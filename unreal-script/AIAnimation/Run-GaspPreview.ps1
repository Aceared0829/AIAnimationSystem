param(
    [string]$Engine = 'D:/UE_5.8',
    [string]$Project = 'D:/GameAnimationSample/GameAnimationSample.uproject',
    [ValidateSet('Benchmark', 'Interactive')][string]$Mode = 'Benchmark',
    [ValidateSet('LastFrame', 'Overlap')][string]$Playback = 'Overlap',
    [ValidateSet(4, 8)][int]$DelayFrames = 8,
    [ValidateRange(0, 240)][int]$MaxFPS = 60,
    [string]$Output
)
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $Output) { $Output = Join-Path $repository ('output/ai_animation_runtime_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) }
$Output = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$editor = Join-Path $Engine 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
if (-not (Test-Path -LiteralPath $editor)) { throw "找不到 UE：$editor" }
if (-not (Test-Path -LiteralPath $Project)) { throw "找不到项目：$Project" }
$map = '/Game/AIAnimationPreview/L_ReconstructionBenchmark'
$arguments = @($Project, $map, '-game', '-windowed', '-ResX=1600', '-ResY=900', '-nosplash', '-NoVSync', "-abslog=$Output/runtime.log")
$streaming = if ($Playback -eq 'Overlap') { 1 } else { 0 }
$arguments += "-ExecCmds=t.MaxFPS $MaxFPS,AIAnimation.Streaming $streaming,AIAnimation.DelayFrames $DelayFrames"
if ($Mode -eq 'Benchmark') {
    $arguments += "-AIAnimationBenchmarkOutput=$Output"
}
& $editor @arguments
if ($LASTEXITCODE -ne 0) { throw "UE 退出码：$LASTEXITCODE；日志：$Output/runtime.log" }
if ($Mode -eq 'Benchmark') {
    $report = Get-Content -LiteralPath (Join-Path $Output 'runtime_report.json') -Raw | ConvertFrom-Json
    $report | ConvertTo-Json -Depth 8
    if (-not $report.passed) { throw '未完成有效的动画工作线程推理，请检查运行报告。' }
}
Write-Host "结果：$Output"
