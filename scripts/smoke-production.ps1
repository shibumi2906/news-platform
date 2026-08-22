param(
  [Parameter(Mandatory)][string]$IntegratorUrl,
  [Parameter(Mandatory)][string]$SiteApiUrl,
  [Parameter(Mandatory)][string]$WebUrl,
  [string]$AdminApiToken = ""
)
$ErrorActionPreference = "Stop"
function Test-Endpoint([string]$Name, [string]$Url, [hashtable]$Headers = @{}) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec 15
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) { throw "HTTP $($response.StatusCode)" }
    Write-Host "OK  $Name"
  } catch { throw "FAILED $Name ($Url): $($_.Exception.Message)" }
}
$integrator = $IntegratorUrl.TrimEnd("/")
$site = $SiteApiUrl.TrimEnd("/")
$web = $WebUrl.TrimEnd("/")
Test-Endpoint "integrator readiness (DB/Redis)" "$integrator/health/ready"
Test-Endpoint "site readiness (DB/Redis/S3)" "$site/health/ready"
Test-Endpoint "public web" "$web/"
Test-Endpoint "public API" "$site/api/v1/public/articles"
if ($AdminApiToken) { Test-Endpoint "admin API" "$site/api/v1/admin/system/status" @{ "X-Admin-Token" = $AdminApiToken } }
else { Write-Host "SKIP admin API (pass -AdminApiToken to verify authenticated availability)" }
Write-Host "Smoke check passed. Provider secrets and values were not printed."
