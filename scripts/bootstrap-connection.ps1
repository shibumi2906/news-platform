param(
  [Parameter(Mandatory)][Guid]$ConnectionId,
  [string]$ProjectName = "news-platform-prod",
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml", "deploy/compose/docker-compose.prod.yml")
)
$ErrorActionPreference = "Stop"
if ($ConnectionId -eq [Guid]::Empty) { throw "ConnectionId must be a nonzero UUID" }
if ($env:CONNECTION_HMAC_SECRET -cnotmatch '^[a-fA-F0-9]{64}$') {
  throw "Set CONNECTION_HMAC_SECRET to a 64-character hex secret"
}

$compose = @("compose", "-p", $ProjectName)
foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }

# Read the secret from stdin. Keep it out of Docker command arguments and logs.
$program = @'
import asyncio
import os
import sys
from uuid import UUID

from common.db import create_engine
from sqlalchemy.dialects.postgresql import insert

kind, connection_id = sys.argv[1:]
secret = input()
if kind == "site":
    from site_domain.models.integrator_connection import IntegratorConnection as model

    fields = {"name": "Integrator"}
else:
    from integrator_domain.models.site_connection import SiteConnection as model

    fields = {"name": "Site", "delivery_url": "http://site-api:8000"}


async def bootstrap():
    engine = create_engine(os.environ["DATABASE_URL"])
    table = model.__table__
    values = dict(id=UUID(connection_id), hmac_secret=secret, is_active=True, **fields)
    if "active_key_id" in table.c:
        values["active_key_id"] = "legacy"
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(table).values(**values).on_conflict_do_nothing(
                index_elements=[table.c.id]
            ))
            row = (await connection.execute(
                table.select().where(table.c.id == values["id"])
            )).mappings().one()
            if any(row[key] != value for key, value in values.items()):
                raise ValueError("Existing connection differs")
    finally:
        await engine.dispose()


try:
    asyncio.run(bootstrap())
except ValueError:
    sys.exit("Existing connection differs from bootstrap settings")
except Exception:
    sys.exit("Could not bootstrap connection. Verify database access and migrations.")
'@

# Register the receiver before enabling the sender. Re-running with the same
# ID and secret can resume after a partial failure without overwriting a key.
foreach ($kind in @("site", "integrator")) {
  $env:CONNECTION_HMAC_SECRET | docker @compose exec -T "$kind-api" python -c $program $kind $ConnectionId
  if ($LASTEXITCODE -ne 0) { throw "$kind connection bootstrap failed" }
  Write-Host "OK  $kind connection $ConnectionId"
}
