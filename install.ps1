<#
  Instalador de J.A.R.V.I.S. — deja JARVIS funcionando igual que en el PC original.

  Uso: doble clic en INSTALAR.cmd  (o: powershell -ExecutionPolicy Bypass -File install.ps1)
  No necesita permisos de administrador. Se puede repetir: solo completa lo que falte.

  Pasos: requisitos (Python 3.12, Ollama, ffmpeg) → entorno con las versiones exactas → interfaz →
  configuración y memoria del paquete → modelos de IA según la GPU → credenciales → accesos directos.
#>
param([switch]$SinPreguntas)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Host.UI.RawUI.WindowTitle = "Instalación de J.A.R.V.I.S."

function Step($t) { Write-Host "`n▸ $t" -ForegroundColor Magenta }
function Ok($t)   { Write-Host "  ✓ $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  ! $t" -ForegroundColor Yellow }
function Fail($t) { Write-Host "  ✗ $t" -ForegroundColor Red; Read-Host "Pulsa Enter para salir"; exit 1 }
function Ask($q, $def = "s") {
  if ($SinPreguntas) { return $def -eq "s" }
  $a = Read-Host "  $q (s/n) [$def]"; if (-not $a) { $a = $def }; return $a -match "^[sSyY]"
}
function Winget($id, $name) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Warn "winget no está disponible: instala $name a mano."; return }
  Write-Host "  ↓ Instalando $name…" -ForegroundColor DarkGray
  winget install -e --id $id --accept-package-agreements --accept-source-agreements --silent --scope user 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) { winget install -e --id $id --accept-package-agreements --accept-source-agreements --silent | Out-Null }
}

Write-Host ""
Write-Host "   J . A . R . V . I . S ." -ForegroundColor Magenta
Write-Host "   Instalación del asistente personal" -ForegroundColor DarkGray
if (Test-Path "$Root\data\MANIFEST.json") {
  $m = Get-Content "$Root\data\MANIFEST.json" -Raw | ConvertFrom-Json
  Write-Host "   Paquete del $($m.created) · versión $($m.version)" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------ 1. requisitos
Step "Comprobando requisitos"
$Py = $null
foreach ($cand in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")) {
  if (Test-Path $cand) { $Py = $cand; break }
}
if (-not $Py) {
  try { $v = & py -3.12 -c "import sys;print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $v) { $Py = $v.Trim() } } catch {}
}
if (-not $Py) {
  Winget "Python.Python.3.12" "Python 3.12"
  foreach ($cand in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:ProgramFiles\Python312\python.exe")) {
    if (Test-Path $cand) { $Py = $cand; break }
  }
}
if (-not $Py) { Fail "No se pudo instalar Python 3.12. Instálalo desde python.org (marca 'Add to PATH') y repite." }
Ok "Python 3.12: $Py"

$Ollama = @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Ollama -and -not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  if (Ask "¿Instalar Ollama para la IA local GRATUITA? (recomendado)") { Winget "Ollama.Ollama" "Ollama" }
}
if ((Get-Command ollama -ErrorAction SilentlyContinue) -or (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")) { Ok "Ollama instalado" } else { Warn "Sin Ollama: solo podrás usar Claude (con API key)" }

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  if (Ask "¿Instalar ffmpeg? (notas de voz de Telegram)") { Winget "Gyan.FFmpeg" "ffmpeg" }
} else { Ok "ffmpeg disponible" }

$Gpu = $null
try { $Gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1) } catch {}
if ($Gpu) { Ok "GPU NVIDIA: $Gpu" } else { Warn "Sin GPU NVIDIA: la voz y la IA local irán por CPU (más lentas)" }

# ------------------------------------------------------------------ 2. entorno Python
Step "Entorno de Python con las versiones exactas"
$VPy = "$Root\.venv\Scripts\python.exe"
if (-not (Test-Path $VPy)) { & $Py -m venv "$Root\.venv"; if ($LASTEXITCODE -ne 0) { Fail "No se pudo crear el entorno" } }
& $VPy -m pip install --upgrade pip -q
$Lock = "$Root\backend\requirements-lock.txt"
if (Test-Path $Lock) {
  & $VPy -m pip install -r $Lock --only-binary av -q
  if ($LASTEXITCODE -ne 0) { Warn "Versiones exactas no disponibles; uso las compatibles"; & $VPy -m pip install "av>=14,<16" --only-binary :all: -q; & $VPy -m pip install -r "$Root\backend\requirements.txt" -q }
} else {
  & $VPy -m pip install "av>=14,<16" --only-binary :all: -q
  & $VPy -m pip install -r "$Root\backend\requirements.txt" -q
}
if ($LASTEXITCODE -ne 0) { Fail "Error instalando dependencias" }
if ($Gpu) {
  Write-Host "  ↓ Aceleración CUDA para la voz (~1,5 GB)…" -ForegroundColor DarkGray
  $GLock = "$Root\backend\requirements-gpu-lock.txt"
  if (Test-Path $GLock) { & $VPy -m pip install -r $GLock -q } else { & $VPy -m pip install -r "$Root\backend\requirements-gpu.txt" -q }
}
Ok "Dependencias instaladas"

# ------------------------------------------------------------------ 3. interfaz
Step "Interfaz"
if (Test-Path "$Root\frontend\dist\index.html") { Ok "Interfaz ya compilada en el paquete" }
elseif (Get-Command npm -ErrorAction SilentlyContinue) {
  Push-Location "$Root\frontend"; npm install --no-audit --no-fund --loglevel=error; npm run build; Pop-Location
  if (-not (Test-Path "$Root\frontend\dist\index.html")) { Fail "Error compilando la interfaz" }
  Ok "Interfaz compilada"
} else { Fail "Falta la interfaz compilada y no hay Node.js. Usa el paquete creado con 'python -m jarvis export'." }

# ------------------------------------------------------------------ 4. configuración y memoria
Step "Configuración y memoria"
Push-Location "$Root\backend"
$Perfil = @("$Root\data\config.portable.yaml", "$Root\perfil\config.portable.yaml") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Perfil) {
  & $VPy -m jarvis import-config "$Perfil"
  Ok "Configuración del PC original aplicada (adaptada a este equipo)"
} else { Ok "Configuración nueva por defecto" }
if (Test-Path "$Root\data\jarvis.db") { Ok "Memoria, tareas y conversaciones restauradas" }

# ------------------------------------------------------------------ 5. modelos
Step "Modelos de IA local y voz (según la GPU de este equipo)"
& $VPy -m jarvis models

# ------------------------------------------------------------------ 6. credenciales
Step "Credenciales (se guardan cifradas en este Windows; no viajan en el paquete)"
Write-Host "  Nota: el mismo bot de Telegram no puede funcionar en dos PCs a la vez." -ForegroundColor DarkGray
Write-Host "  Para usar Telegram en los dos, crea otro bot con @BotFather para este portátil." -ForegroundColor DarkGray
& $VPy -m jarvis setup

# ------------------------------------------------------------------ 7. accesos directos
Step "Accesos directos"
& $VPy -m jarvis shortcut
if (Ask "¿Iniciar JARVIS automáticamente al encender el PC?") { & $VPy -m jarvis autostart on }
Step "Diagnóstico"
& $VPy -m jarvis doctor
Pop-Location

Write-Host "`n  Instalación completada." -ForegroundColor Green
Write-Host "  Abre JARVIS con el acceso directo del escritorio. Di «Hey JARVIS» para hablarle.`n" -ForegroundColor Gray
if (Ask "¿Iniciar JARVIS ahora?") { Start-Process "$Root\Jarvis.cmd" -WindowStyle Hidden }
