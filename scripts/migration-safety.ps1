param(
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml"),
  [string]$ProjectName = ""
)
$ErrorActionPreference = "Stop"
$compose = @("compose")
foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }
if ($ProjectName) { $compose += @("-p", $ProjectName) }
$integratorHeads = @(docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini heads)
if ($LASTEXITCODE -ne 0) { throw "Integrator migration graph is invalid" }
if (@($integratorHeads | Where-Object { $_ -match "\(head\)" }).Count -ne 1) { throw "Integrator migration graph must have exactly one head" }
$siteHeads = @(docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini heads)
if ($LASTEXITCODE -ne 0) { throw "Site migration graph is invalid" }
if (@($siteHeads | Where-Object { $_ -match "\(head\)" }).Count -ne 1) { throw "Site migration graph must have exactly one head" }
docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw "Integrator migration failed" }
docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw "Site migration failed" }
docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini check
if ($LASTEXITCODE -ne 0) { throw "Integrator ORM metadata differs from the migrated schema" }
docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini check
if ($LASTEXITCODE -ne 0) { throw "Site ORM metadata differs from the migrated schema" }
