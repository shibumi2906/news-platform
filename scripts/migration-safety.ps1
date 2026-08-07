param(
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml"),
  [string]$ProjectName = ""
)
$ErrorActionPreference = "Stop"
$compose = @("compose")
foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }
if ($ProjectName) { $compose += @("-p", $ProjectName) }
docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini heads
if ($LASTEXITCODE -ne 0) { throw "Integrator migration graph is invalid" }
docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini heads
if ($LASTEXITCODE -ne 0) { throw "Site migration graph is invalid" }
docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw "Integrator migration failed" }
docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini upgrade head
if ($LASTEXITCODE -ne 0) { throw "Site migration failed" }
