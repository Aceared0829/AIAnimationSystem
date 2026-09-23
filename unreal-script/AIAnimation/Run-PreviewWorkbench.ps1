param(
    [string]$Engine = 'D:/UE_5.8',
    [string]$Project = 'D:/GameAnimationSample/GameAnimationSample.uproject',
    [ValidateRange(15, 120)][int]$MaxFPS = 30
)

$ErrorActionPreference = 'Stop'
$editor = Join-Path $Engine 'Engine/Binaries/Win64/UnrealEditor.exe'
if (-not (Test-Path -LiteralPath $editor)) { throw "找不到 UnrealEditor：$editor" }
if (-not (Test-Path -LiteralPath $Project)) { throw "找不到 UE 项目：$Project" }

$arguments = @(
    ('"{0}"' -f [IO.Path]::GetFullPath($Project)),
    '-NoSplash',
    '-NoSound',
    '-NoLoadStartupPackages',
    '-ini:EditorPerProjectUserSettings:[/Script/UnrealEd.EditorLoadingSavingSettings]:LoadLevelAtStartup=None',
    ('"-ExecCmds=AIAnimation.OpenWorkbenchOnly,t.MaxFPS {0}"' -f $MaxFPS)
)

$process = Start-Process -FilePath $editor -ArgumentList $arguments -PassThru
Write-Host "AIAnimation 工作台正在启动；UnrealEditor PID：$($process.Id)"
