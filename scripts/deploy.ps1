param(
  [ValidateSet("install", "update", "rollback")][string]$Action,
  [string]$BaseCompose = "deploy/compose/docker-compose.dev.yml",
  [string]$ProductionCompose = "deploy/compose/docker-compose.prod.yml",
  [string[]]$AdditionalCompose = @(),
  [string]$ProjectName = "",
  [switch]$RollbackDatabase
)
$ErrorActionPreference = "Stop"
& "$PSScriptRoot/validate-production-env.ps1" -Quiet
$compose = @("compose", "-f", $BaseCompose, "-f", $ProductionCompose)
foreach ($file in $AdditionalCompose) { $compose += @("-f", $file) }
if ($ProjectName) { $compose += @("-p", $ProjectName) }
if ($Action -eq "install") {
  docker @compose up --build --detach --wait
  if ($LASTEXITCODE -ne 0) { throw "install failed" }
} elseif ($Action -eq "update") {
  docker @compose build --pull
  if ($LASTEXITCODE -ne 0) { throw "update build failed" }
  docker @compose run --rm migrate-integrator
  if ($LASTEXITCODE -ne 0) { throw "integrator migration failed" }
  docker @compose run --rm migrate-site
  if ($LASTEXITCODE -ne 0) { throw "site migration failed" }
  docker @compose up --detach --wait --remove-orphans
  if ($LASTEXITCODE -ne 0) { throw "update startup failed" }
} else {
  if ($RollbackDatabase) {
    docker @compose run --rm migrate-integrator alembic -c migrations/integrator/alembic.ini downgrade -1
    if ($LASTEXITCODE -ne 0) { throw "integrator rollback failed" }
    docker @compose run --rm migrate-site alembic -c migrations/site/alembic.ini downgrade -1
    if ($LASTEXITCODE -ne 0) { throw "site rollback failed" }
  }
  docker @compose up --detach --wait --no-build
  if ($LASTEXITCODE -ne 0) { throw "application rollback startup failed" }
}
