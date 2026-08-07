param(
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml"),
  [string]$ProjectName = "",
  [string]$OutputDirectory = "backups"
)
$ErrorActionPreference = "Stop"
$compose = @("compose")
foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }
if ($ProjectName) { $compose += @("-p", $ProjectName) }
$target = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $target -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$site = Join-Path $target "site-$stamp.dump"
$integrator = Join-Path $target "integrator-$stamp.dump"
docker @compose exec -T postgres-site pg_dump -U news_platform -d news_platform_site -Fc -f /tmp/site.dump
if ($LASTEXITCODE -ne 0) { throw "Site PostgreSQL backup failed" }
docker @compose cp postgres-site:/tmp/site.dump $site
if ($LASTEXITCODE -ne 0) { throw "Site backup copy failed" }
docker @compose exec -T postgres-integrator pg_dump -U news_platform -d news_platform_integrator -Fc -f /tmp/integrator.dump
if ($LASTEXITCODE -ne 0) { throw "Integrator PostgreSQL backup failed" }
docker @compose cp postgres-integrator:/tmp/integrator.dump $integrator
if ($LASTEXITCODE -ne 0) { throw "Integrator backup copy failed" }
$minioId = docker @compose ps -q minio
if ([string]::IsNullOrWhiteSpace($minioId)) { throw "MinIO container is not running" }
$media = Join-Path $target "minio-$stamp.tar.gz"
docker run --rm --volumes-from $minioId -v "${target}:/backup" alpine:3.20 tar -czf "/backup/$(Split-Path $media -Leaf)" -C /data .
if ($LASTEXITCODE -ne 0) { throw "MinIO backup failed" }
$files = @($site, $integrator, $media)
$manifest = @{ created_at = [DateTime]::UtcNow.ToString("o"); files = @() }
foreach ($file in $files) {
  $manifest.files += @{ name = (Split-Path $file -Leaf); sha256 = (Get-FileHash $file -Algorithm SHA256).Hash.ToLower() }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $target "manifest-$stamp.json") -Encoding UTF8
Write-Host "Backup completed: $target (credentials and application payloads omitted from output)."
