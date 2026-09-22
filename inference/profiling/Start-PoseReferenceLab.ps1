$ErrorActionPreference = 'Stop'
$labRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$labUrl = 'http://127.0.0.1:8769'
$labRunning = $false
try {
    $labInfo = Invoke-RestMethod "$labUrl/api/init" -TimeoutSec 2
    $labRunning = [bool]$labInfo.asset
} catch { }
if (-not $labRunning) {
    $labLog = Join-Path $labRoot '.build'
    New-Item -ItemType Directory -Force -Path $labLog | Out-Null
    Start-Process -FilePath (Join-Path $labRoot '.venv/Scripts/python.exe') `
        -ArgumentList '-m','inference.profiling.pose_reference_lab','--port','8769' `
        -WorkingDirectory $labRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $labLog 'pose_lab_stdout.log') `
        -RedirectStandardError (Join-Path $labLog 'pose_lab_stderr.log') | Out-Null
    for ($labAttempt = 0; $labAttempt -lt 30; $labAttempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $labInfo = Invoke-RestMethod "$labUrl/api/init" -TimeoutSec 1
            if ($labInfo.asset) { $labRunning = $true; break }
        } catch { }
    }
}
if (-not $labRunning) { throw '实验室启动失败，请检查 .build/pose_lab_stderr.log' }
Start-Process $labUrl
