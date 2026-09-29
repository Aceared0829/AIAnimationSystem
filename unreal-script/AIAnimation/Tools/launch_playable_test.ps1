$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$project = Join-Path $workspace 'output\ue_cmc_host\Host.uproject'
$bundle = Join-Path $workspace 'output\playable_player_20260927\bundle'
$editor = 'D:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'

foreach ($path in @($project, $editor, (Join-Path $bundle 'manifest.json'))) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Playable test dependency missing: $path"
    }
}

$env:AIANIMATION_PLAYABLE_BUNDLE = (Resolve-Path -LiteralPath $bundle).Path
$map = '/Engine/Maps/Entry?game=/Script/AIAnimation.AIAnimationPlayableGameMode'
$arguments = @($project, $map, '-game', '-windowed', '-ResX=1024', '-ResY=600', '-NoSplash', '-NoP4')
$process = Start-Process -FilePath $editor -ArgumentList $arguments -WorkingDirectory $workspace -PassThru
Write-Output "UE playable test started. PID=$($process.Id)"
Write-Output 'Controls: WASD move, mouse/QE turn, Left Shift run, C crouch, 1/2 model, R reset.'
Write-Output (Join-Path $workspace 'output\ue_cmc_host\Saved\Logs')
