# Copyright ZhaoZining. All Rights Reserved.

param(
    [string]$ModelFolder = 'E:\AIAnimationSystemData\exports\stance_pilot_b1_ue_20260928_v3',
    [switch]$Feedback,
    [switch]$AutoTest
)

$EditorPath = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$ProjectPath = 'D:\GameAnimationSample\GameAnimationSample.uproject'
if (-not (Test-Path -LiteralPath $EditorPath)) { throw "UE 编辑器不存在：$EditorPath" }
if (-not (Test-Path -LiteralPath $ProjectPath)) { throw "GASP 项目不存在：$ProjectPath" }
foreach ($RequiredFile in @('model.onnx', 'manifest.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ModelFolder $RequiredFile))) {
        throw "模型导出文件不存在：$RequiredFile，目录 $ModelFolder"
    }
}

$PreviewArgs = @(
    $ProjectPath,
    '/MotionWeaverCMCPreview/Maps/L_CMCPreview',
    '-game', '-windowed', '-ResX=1280', '-ResY=720', '-NoSplash',
    "-MotionWeaverModelFolder=$ModelFolder"
)
if ($Feedback) { $PreviewArgs += '-MotionWeaverFeedback' }
if ($AutoTest) { $PreviewArgs += '-MotionWeaverAutoTest' }

$PreviewProcess = Start-Process -FilePath $EditorPath -ArgumentList $PreviewArgs -PassThru
Write-Output "MotionWeaver B1 UE 预览 PID=$($PreviewProcess.Id)，反馈历史=$Feedback，自动测试=$AutoTest"
if ($AutoTest) {
    $PreviewProcess.WaitForExit()
    if ($PreviewProcess.ExitCode -ne 0) { throw "UE 自动场景失败，退出码 $($PreviewProcess.ExitCode)；请检查 D:\GameAnimationSample\Saved\Logs\GameAnimationSample.log" }
}
