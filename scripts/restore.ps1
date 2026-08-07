param(
  [Parameter(Mandatory)][string]$BackupDirectory,
  [Parameter(Mandatory)][string]$Stamp,
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml"),
  [string]$ProjectName = "",
  [switch]$ConfirmRestore
)
$ErrorActionPreference = "Stop"
$compose = @("compose")
foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }
if ($ProjectName) { $compose += @("-p", $ProjectName) }
if (-not $ConfirmRestore) { throw "Restore is destructive; pass -ConfirmRestore after validating the target environment" }
$target = [IO.Path]::GetFullPath($BackupDirectory)
$manifestPath = Join-Path $target "manifest-$Stamp.json"
$manifest = Get-Content $manifestPath | ConvertFrom-Json
foreach ($entry in $manifest.files) {
  $file = Join-Path $target $entry.name
  if ((Get-FileHash $file -Algorithm SHA256).Hash.ToLower() -ne $entry.sha256) { throw "Backup checksum failed: $($entry.name)" }
}
$site = Join-Path $target "site-$Stamp.dump"
$integrator = Join-Path $target "integrator-$Stamp.dump"
$runtime = @("public-web", "site-api", "integrator-api", "source-worker", "source-worker-beat", "processing-worker", "processing-worker-beat", "delivery-worker", "delivery-worker-beat", "distribution-worker", "distribution-worker-beat")
docker @compose stop @runtime
if ($LASTEXITCODE -ne 0) { throw "Could not stop runtime services" }
docker @compose cp $site postgres-site:/tmp/site.dump
if ($LASTEXITCODE -ne 0) { throw "Site restore copy failed" }
docker @compose exec -T postgres-site pg_restore -U news_platform -d news_platform_site --clean --if-exists /tmp/site.dump
if ($LASTEXITCODE -ne 0) { throw "Site PostgreSQL restore failed" }
docker @compose cp $integrator postgres-integrator:/tmp/integrator.dump
if ($LASTEXITCODE -ne 0) { throw "Integrator restore copy failed" }
docker @compose exec -T postgres-integrator pg_restore -U news_platform -d news_platform_integrator --clean --if-exists /tmp/integrator.dump
if ($LASTEXITCODE -ne 0) { throw "Integrator PostgreSQL restore failed" }
docker @compose stop minio
if ($LASTEXITCODE -ne 0) { throw "Could not stop MinIO" }
$minioId = docker @compose ps -aq minio
$media = Join-Path $target "minio-$Stamp.tar.gz"
docker run --rm --volumes-from $minioId -v "${target}:/backup" alpine:3.20 sh -c "rm -rf /data/* && tar -xzf /backup/$(Split-Path $media -Leaf) -C /data"
if ($LASTEXITCODE -ne 0) { throw "MinIO restore failed" }
docker @compose start minio
if ($LASTEXITCODE -ne 0) { throw "Could not restart MinIO" }
docker @compose start @runtime
if ($LASTEXITCODE -ne 0) { throw "Could not restart runtime services" }
Write-Host "Restore completed and checksums verified. Run readiness and application smoke tests now."
