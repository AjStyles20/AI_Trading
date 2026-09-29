$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot '../frontend/backend-bundle/astral-backend/astral-backend.exe'
$data = Join-Path $env:RUNNER_TEMP 'astral-smoke-data'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$env:ASTRAL_DATA_DIR = $data
$env:ASTRAL_DESKTOP_TOKEN = [guid]::NewGuid().ToString('N')
$process = Start-Process -FilePath $exe -PassThru -NoNewWindow
try {
    $ready = $false
    for ($i = 0; $i -lt 180; $i++) {
        if ($process.HasExited) { throw "Backend exited with code $($process.ExitCode)" }
        try {
            $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/desktop/health' -Headers @{ 'x-astral-desktop-token' = $env:ASTRAL_DESKTOP_TOKEN } -TimeoutSec 2
            if ($response.service -eq 'astral-backend') { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Bundled backend did not become healthy' }
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/settings' -UseBasicParsing -TimeoutSec 3 | Out-Null
        throw 'API accepted an unauthenticated request'
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 401) { throw }
    }
    $authorized = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/settings' -Headers @{ 'x-astral-desktop-token' = $env:ASTRAL_DESKTOP_TOKEN } -TimeoutSec 5
    if (-not $authorized) { throw 'Authorized API request returned no settings' }
} finally {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Remove-Item Env:ASTRAL_DESKTOP_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:ASTRAL_DATA_DIR -ErrorAction SilentlyContinue
}
