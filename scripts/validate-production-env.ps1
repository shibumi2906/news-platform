param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$required = @(
  "POSTGRES_INTEGRATOR_PASSWORD", "POSTGRES_SITE_PASSWORD", "REDIS_PASSWORD",
  "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "ADMIN_API_TOKEN", "ADMIN_SESSION_KEYS",
  "ADMIN_BOOTSTRAP_USERNAME", "ADMIN_BOOTSTRAP_PASSWORD", "API_ALLOWED_HOSTS", "WEB_ORIGIN"
)
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
if ($missing.Count -gt 0) { throw "Missing required production variables: $($missing -join ', ')" }
foreach ($name in $required) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if ($value -match "change-me" -or ($name -ne "API_ALLOWED_HOSTS" -and $value -match "localhost")) {
    throw "Unsafe placeholder detected in $name"
  }
}
if ([Environment]::GetEnvironmentVariable("ADMIN_SESSION_KEYS") -notmatch "^[A-Za-z0-9._-]+:.{32,}") {
  throw "ADMIN_SESSION_KEYS must use kid:secret with at least 32 secret characters"
}
if (-not $Quiet) { Write-Host "Production environment validation passed (secret values omitted)." }
