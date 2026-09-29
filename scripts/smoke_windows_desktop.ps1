$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot '../frontend/release/win-unpacked/Astral AI Trading.exe'
if (-not (Test-Path $exe)) { throw 'Unpacked Electron executable is missing' }
$process = Start-Process -FilePath $exe -ArgumentList '--smoke-test' -PassThru
try {
    Wait-Process -Id $process.Id -Timeout 150 -ErrorAction Stop
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Desktop renderer/API smoke test failed with code $($process.ExitCode)" }
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
}
