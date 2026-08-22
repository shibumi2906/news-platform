param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$required = @(
  "POSTGRES_INTEGRATOR_PASSWORD", "POSTGRES_SITE_PASSWORD", "REDIS_PASSWORD",
  "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "ADMIN_API_TOKEN", "ADMIN_SESSION_KEYS",
  "API_ALLOWED_HOSTS", "WEB_ORIGIN", "INTEGRATOR_INSTANCE_ID", "SITE_INSTANCE_ID",
  "WEB_DOMAIN", "SITE_API_DOMAIN", "ACME_EMAIL", "AI_PROVIDERS"
)
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
if ($missing.Count -gt 0) { throw "Missing required production variables: $($missing -join ', ')" }
foreach ($name in $required) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if ($value -match "change-me" -or ($name -ne "API_ALLOWED_HOSTS" -and $value -match "localhost")) {
    throw "Unsafe placeholder detected in $name"
  }
}
$integratorId = $null; $siteId = $null
if (-not [Guid]::TryParse([Environment]::GetEnvironmentVariable("INTEGRATOR_INSTANCE_ID"), [ref]$integratorId)) { throw "INTEGRATOR_INSTANCE_ID must be a UUID" }
if (-not [Guid]::TryParse([Environment]::GetEnvironmentVariable("SITE_INSTANCE_ID"), [ref]$siteId)) { throw "SITE_INSTANCE_ID must be a UUID" }
if ($integratorId -eq $siteId) { throw "INTEGRATOR_INSTANCE_ID and SITE_INSTANCE_ID must differ" }
if ([Environment]::GetEnvironmentVariable("ADMIN_API_TOKEN").Length -lt 32) {
  throw "ADMIN_API_TOKEN must contain at least 32 characters"
}
$sessionKeyIds = @{}
foreach ($entry in [Environment]::GetEnvironmentVariable("ADMIN_SESSION_KEYS").Split(",")) {
  if ($entry -notmatch "^([A-Za-z0-9._-]+):(.{32,})$") {
    throw "Every ADMIN_SESSION_KEYS entry must use kid:secret with at least 32 secret characters"
  }
  if ($sessionKeyIds.ContainsKey($Matches[1])) { throw "ADMIN_SESSION_KEYS contains a duplicate key id" }
  $sessionKeyIds[$Matches[1]] = $true
}
$hosts = [Environment]::GetEnvironmentVariable("API_ALLOWED_HOSTS").Split(",") | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
if ($hosts.Count -eq 0 -or $hosts -contains "*") { throw "API_ALLOWED_HOSTS must be explicit" }
foreach ($origin in [Environment]::GetEnvironmentVariable("WEB_ORIGIN").Split(",")) {
  $uri = $null
  if (-not [Uri]::TryCreate($origin, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne "https") {
    throw "WEB_ORIGIN must contain absolute HTTPS origins"
  }
}
$aiProviders = [Environment]::GetEnvironmentVariable("AI_PROVIDERS")
if ([string]::IsNullOrWhiteSpace($aiProviders) -or $aiProviders.Split(",") -contains "fake") {
  throw "AI_PROVIDERS must name production providers and must not include fake"
}
if ($aiProviders.Split(",") -contains "openai" -and [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("OPENAI_API_KEY"))) {
  throw "OPENAI_API_KEY is required when AI_PROVIDERS includes openai"
}
$bootstrapUsername = [Environment]::GetEnvironmentVariable("ADMIN_BOOTSTRAP_USERNAME")
$bootstrapPassword = [Environment]::GetEnvironmentVariable("ADMIN_BOOTSTRAP_PASSWORD")
if ([string]::IsNullOrWhiteSpace($bootstrapUsername) -ne [string]::IsNullOrWhiteSpace($bootstrapPassword)) {
  throw "ADMIN_BOOTSTRAP_USERNAME and ADMIN_BOOTSTRAP_PASSWORD must be set together"
}
if (-not [string]::IsNullOrWhiteSpace($bootstrapPassword) -and $bootstrapPassword.Length -lt 12) {
  throw "ADMIN_BOOTSTRAP_PASSWORD must contain at least 12 characters"
}
if (-not $Quiet) { Write-Host "Production environment validation passed (secret values omitted)." }
