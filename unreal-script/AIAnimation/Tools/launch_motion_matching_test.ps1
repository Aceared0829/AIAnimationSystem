$ErrorActionPreference = 'Stop'

$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
& (Join-Path $PSScriptRoot 'setup_motion_matching_host.ps1') | Out-Null
$project = Join-Path $workspace 'output\ue_cmc_host\Host.uproject'
$bundle = Join-Path $workspace 'output\playable_player_20260927\bundle'
$animBlueprint = Join-Path $workspace 'output\ue_cmc_host\Saved\AIAnimation\MotionMatchingPrepared.txt'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'

foreach ($path in @($project, $editor, (Join-Path $bundle 'manifest.json'), $animBlueprint)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Motion Matching live test dependency missing: $path"
    }
}

$env:AIANIMATION_PLAYABLE_BUNDLE = (Resolve-Path -LiteralPath $bundle).Path
$map = '/Engine/Maps/Entry?game=/Script/AIAnimationMotionMatching.AIAnimationMotionMatchingGameMode'
$arguments = @($project, $map, '-game', '-windowed', '-ResX=1100', '-ResY=680', '-NoSplash', '-NoP4')
$process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $workspace -PassThru
Write-Output "MotionMatchingInCpp + AIAnimation test started. PID=$($process.Id)"
Write-Output 'Controls: WASD / mouse, Shift sprint, C crouch, 1 Motion Matching, 2 control model, 3 speed model, R reset, Esc exit.'
Write-Output (Join-Path $workspace 'output\ue_cmc_host\Saved\Logs')
