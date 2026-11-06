<#
.SYNOPSIS
  Despliega el harness genérico a ~/.claude y el perfil al proyecto destino.
.EXAMPLE
  .\deploy.ps1 -Proyecto "C:\ruta\al\proyecto" -Perfil crud-api
.EXAMPLE
  .\deploy.ps1 -Proyecto "C:\ruta\al\proyecto" -SinHooks
  # no toca settings.json: imprime el bloque de hooks para pegarlo a mano
#>
param(
  [Parameter(Mandatory = $true)][string]$Proyecto,
  [string]$Perfil = "crud-api",
  [switch]$SinHooks
)

$ErrorActionPreference = "Stop"
$Fuente = $PSScriptRoot
$Global = Join-Path $env:USERPROFILE ".claude"

if (-not (Test-Path $Proyecto)) { throw "No existe el proyecto: $Proyecto" }
$RutaPerfil = Join-Path $Fuente "profiles\$Perfil"
if (-not (Test-Path $RutaPerfil)) { throw "No existe el perfil: $RutaPerfil" }

# --- Harness genérico -> ~/.claude ---
foreach ($sub in @("hooks", "agents", "skills", "commands")) {
  $origen = Join-Path $Fuente "harness\$sub"
  if (-not (Test-Path $origen)) { continue }
  $destino = Join-Path $Global $sub
  New-Item -ItemType Directory -Force -Path $destino | Out-Null
  # probe_hook.py es la sonda temporal que documentó los payloads: no es parte
  # del harness final y no tiene por qué vivir en ~/.claude.
  Copy-Item -Path (Join-Path $origen "*") -Destination $destino -Recurse -Force `
            -Exclude "probe_hook.py"
  Write-Host "harness/$sub -> $destino"
}

# --- Perfil -> <proyecto>/.claude ---
$DestinoPerfil = Join-Path $Proyecto ".claude"
New-Item -ItemType Directory -Force -Path $DestinoPerfil | Out-Null
Copy-Item -Path (Join-Path $RutaPerfil "*") -Destination $DestinoPerfil -Recurse -Force
Write-Host "profiles/$Perfil -> $DestinoPerfil"

# --- .gitignore del proyecto: el estado arranca sin versionar ---
$GitIgnore = Join-Path $Proyecto ".gitignore"
$Linea = ".harness/"
if (-not (Test-Path $GitIgnore)) { New-Item -ItemType File -Path $GitIgnore | Out-Null }
if (-not (Select-String -Path $GitIgnore -SimpleMatch $Linea -Quiet)) {
  Add-Content -Path $GitIgnore -Value $Linea -Encoding utf8
  Write-Host "Agregado '$Linea' al .gitignore del proyecto"
}

# --- Hooks en settings.json ---
$Settings = Join-Path $Global "settings.json"

if ($SinHooks) {
  $HookCheck = (Join-Path $Global "hooks\check_rules.py") -replace '\\', '\\'
  $HookGate  = (Join-Path $Global "hooks\gate_phase.py")  -replace '\\', '\\'

  Write-Host ""
  Write-Host "Con -SinHooks no se toca $Settings. Registra los hooks a mano:"
  Write-Host "Fusiona esto dentro del objeto 'hooks' existente (no reemplaces el archivo):"
  Write-Host ""
  Write-Host @"
"PostToolUse": [
  { "matcher": "Edit|Write|MultiEdit",
    "hooks": [{ "type": "command", "command": "python \"$HookCheck\"" }] }
],
"Stop": [
  { "matcher": "",
    "hooks": [{ "type": "command", "command": "python \"$HookGate\"" }] }
]
"@
}
else {
  # registrar_hooks.py avisa qué hizo y respalda settings.json con fecha y hora
  # solo si lo escribe; con un JSON roto sale con 1 sin escribir nada.
  & python (Join-Path $Fuente "registrar_hooks.py") --settings $Settings --hooks-dir (Join-Path $Global "hooks")
  if ($LASTEXITCODE -ne 0) {
    throw "registrar_hooks.py falló (ver el mensaje de arriba); settings.json quedó como estaba ($Settings). Usa -SinHooks para registrarlos a mano."
  }
}
