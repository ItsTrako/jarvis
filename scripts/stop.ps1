# Detiene J.A.R.V.I.S. de forma ordenada usando la API local (token de sesión).
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$tokenFile = Join-Path $Root "data\.session_token"
$port = 8765
try {
  $cfg = Get-Content (Join-Path $Root "data\config.yaml") -Raw -ErrorAction Stop
  if ($cfg -match "port:\s*(\d+)") { $port = [int]$Matches[1] }
} catch {}
if (-not (Test-Path $tokenFile)) { Write-Host "JARVIS no parece estar en ejecución."; exit 0 }
try {
  $token = (Get-Content $tokenFile -Raw).Trim()
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/shutdown" -Headers @{ "X-Jarvis-Token" = $token } -TimeoutSec 5 | Out-Null
  Write-Host "JARVIS se está deteniendo."
} catch {
  Write-Host "No se pudo contactar con JARVIS (puede que ya esté detenido)."
}
