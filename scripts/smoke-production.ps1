param(
  [string]$IntegratorUrl,
  [Parameter(Mandatory)][string]$SiteApiUrl,
  [Parameter(Mandatory)][string]$WebUrl,
  [string]$AdminApiToken = "",
  [string[]]$ComposeFiles = @("deploy/compose/docker-compose.dev.yml", "deploy/compose/docker-compose.prod.yml"),
  [string]$ProjectName = "news-platform-prod"
)
$ErrorActionPreference = "Stop"
function Test-Endpoint([string]$Name, [string]$Url, [hashtable]$Headers = @{}) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec 15
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) { throw "HTTP $($response.StatusCode)" }
    Write-Host "OK  $Name"
  } catch { throw "FAILED $Name ($Url): $($_.Exception.Message)" }
}
$site = $SiteApiUrl.TrimEnd("/")
$web = $WebUrl.TrimEnd("/")
if ($IntegratorUrl) {
  Test-Endpoint "integrator readiness (DB/Redis)" "$($IntegratorUrl.TrimEnd('/'))/health/ready"
} else {
  $compose = @("compose", "-p", $ProjectName)
  foreach ($file in $ComposeFiles) { $compose += @("-f", $file) }
  docker @compose exec -T integrator-api curl --fail --silent --show-error --max-time 15 --output /dev/null http://localhost:8000/health/ready
  if ($LASTEXITCODE -ne 0) { throw "FAILED Integrator readiness (DB/Redis)" }
  Write-Host "OK  integrator readiness (DB/Redis)"
}
Test-Endpoint "site readiness (DB/Redis/S3)" "$site/health/ready"
Test-Endpoint "public web" "$web/"
Test-Endpoint "public API" "$site/api/v1/public/articles"
if ($AdminApiToken) { Test-Endpoint "admin API" "$site/api/v1/admin/system/status" @{ "X-Admin-Token" = $AdminApiToken } }
else { Write-Host "SKIP admin API (pass -AdminApiToken to verify authenticated availability)" }
Write-Host "Smoke check passed. Provider secrets and values were not printed."
