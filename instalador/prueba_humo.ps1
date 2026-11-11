# Prueba de humo del ejecutable ya construido: arranca el servidor local con PostgreSQL
# embebido, recorre la instalacion inicial y los ajustes, y abre la ventana de la app.
# Usa una carpeta de datos temporal; no toca una instalacion real.

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $raiz "dist\CreeAgenda\CreeAgenda.exe"
$env:CREE_DIR_DATOS = Join-Path $env:TEMP ("cree-humo-" + [guid]::NewGuid().ToString("N"))
$env:CREE_DIR_POSTGRES = Join-Path $raiz "build\postgres\bin"
$api = "http://127.0.0.1:8765"

function Mostrar-Registros {
  Get-ChildItem -Recurse $env:CREE_DIR_DATOS -Filter *.log -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "----- $($_.FullName)"; Get-Content $_.FullName -Tail 60
  }
}

try {
  Start-Process -FilePath $exe -ArgumentList "--servidor"
  $listo = $false
  foreach ($i in 1..150) {
    try { if ((Invoke-RestMethod "$api/health" -TimeoutSec 2).estado -eq "ok") { $listo = $true; break } } catch { }
    Start-Sleep -Seconds 1
  }
  if (-not $listo) { throw "El servidor local no respondio" }
  Write-Host "Servidor listo tras $i s"

  $estado = Invoke-RestMethod "$api/api/instalacion/estado"
  if (-not ($estado.modo_local -and $estado.requiere_admin)) { throw "Estado de instalacion inesperado" }

  $cuenta = @{ nombre = "Humo"; correo = "humo@cree.test"; password = "clave-de-humo-1" } | ConvertTo-Json
  Invoke-RestMethod "$api/api/instalacion/admin" -Method Post -Body $cuenta -ContentType "application/json" | Out-Null
  $acceso = @{ correo = "humo@cree.test"; password = "clave-de-humo-1" } | ConvertTo-Json
  $token = (Invoke-RestMethod "$api/api/auth/login" -Method Post -Body $acceso -ContentType "application/json").access_token
  $cabeceras = @{ Authorization = "Bearer $token" }

  $cambio = @{ gemini_model = "gemini-flash-latest" } | ConvertTo-Json
  $ajustes = Invoke-RestMethod "$api/api/ajustes" -Method Put -Body $cambio -ContentType "application/json" -Headers $cabeceras
  if ($ajustes.valores.gemini_model -ne "gemini-flash-latest") { throw "Los ajustes no se guardaron" }

  # Zonas horarias (tzdata) y cifrado: crear doctor, paciente y cita.
  $doctor = Invoke-RestMethod "$api/api/doctores" -Method Post -Headers $cabeceras -ContentType "application/json" `
    -Body (@{ nombre = "Dra. Humo"; telefono_whatsapp = "+525511223344"; zona_horaria = "America/Mexico_City" } | ConvertTo-Json)
  $paciente = Invoke-RestMethod "$api/api/pacientes" -Method Post -Headers $cabeceras -ContentType "application/json" `
    -Body (@{ nombre_completo = "Paciente Humo"; notas_clinicas_breves = "nota" } | ConvertTo-Json)
  $inicio = (Get-Date).ToUniversalTime().AddDays(1).ToString("yyyy-MM-ddT17:00:00Z")
  $cita = Invoke-RestMethod "$api/api/citas" -Method Post -Headers $cabeceras -ContentType "application/json" `
    -Body (@{ id_doctor = $doctor.id; id_paciente = $paciente.id; fecha_hora_inicio = $inicio } | ConvertTo-Json)
  if ($cita.estado -ne "programada") { throw "No se pudo crear la cita" }
  $kpis = Invoke-RestMethod "$api/api/dashboard/kpis" -Headers $cabeceras
  Write-Host "API verificada (cita $($cita.id))"

  if ((Invoke-RestMethod "http://127.0.0.1:8766/health").estado -ne "ok") { throw "El webhook no responde" }

  # Ventana de la app: debe abrir y seguir viva.
  $ventana = Start-Process -FilePath $exe -PassThru
  Start-Sleep -Seconds 25
  if ($ventana.HasExited) { throw "La app de escritorio se cerro sola (codigo $($ventana.ExitCode))" }
  $cliente = Get-Process | Where-Object { $_.ProcessName -like "flet*" }
  if (-not $cliente) { throw "No se abrio la ventana de la app" }
  Write-Host "Ventana de la app abierta"
  $cliente | Stop-Process -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $ventana.Id -Force -ErrorAction SilentlyContinue

  & $exe --detener | Out-Null
  Start-Sleep -Seconds 5
  try { Invoke-RestMethod "$api/health" -TimeoutSec 2 | Out-Null; throw "El servidor siguio activo tras --detener" }
  catch { if ($_.Exception.Message -like "*siguio activo*") { throw } }
  Write-Host "PRUEBA DE HUMO CORRECTA"
}
catch {
  Mostrar-Registros
  throw
}
