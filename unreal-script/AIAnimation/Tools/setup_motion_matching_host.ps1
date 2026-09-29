$ErrorActionPreference = 'Stop'

$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$hostRoot = Join-Path $workspace 'output\ue_cmc_host'
$projectPath = Join-Path $hostRoot 'Host.uproject'
$pluginSource = 'D:\UnrealDataEngine\UrealDataEngine\Plugins\MotionMatchingInCpp'
$pluginLink = Join-Path $hostRoot 'Plugins\MotionMatchingInCpp'
$bridgeSource = Join-Path $workspace 'unreal-script\AIAnimationMotionMatching'
$bridgeLink = Join-Path $hostRoot 'Plugins\AIAnimationMotionMatching'
$tagSource = 'D:\UnrealDataEngine\UrealDataEngine\Config\DefaultGameplayTags.ini'
$tagTarget = Join-Path $hostRoot 'Config\DefaultGameplayTags.ini'
$gameTarget = Join-Path $hostRoot 'Config\DefaultGame.ini'
$engineSource = 'D:\UnrealDataEngine\UrealDataEngine\Config\DefaultEngine.ini'
$engineTarget = Join-Path $hostRoot 'Config\DefaultEngine.ini'

foreach ($path in @($projectPath, (Join-Path $pluginSource 'MotionMatchingInCpp.uplugin'), (Join-Path $bridgeSource 'AIAnimationMotionMatching.uplugin'), $tagSource, $engineSource)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Motion Matching host dependency missing: $path"
    }
}

Copy-Item -LiteralPath $tagSource -Destination $tagTarget -Force
$engineLines = Get-Content -LiteralPath $engineSource
$sectionStart = [Array]::IndexOf($engineLines, '[/Script/Engine.DataDrivenConsoleVariableSettings]')
if ($sectionStart -lt 0) {
    throw "Missing DataDrivenConsoleVariableSettings in $engineSource"
}
$sectionEnd = $sectionStart + 1
while ($sectionEnd -lt $engineLines.Length -and -not $engineLines[$sectionEnd].StartsWith('[')) {
    $sectionEnd++
}
$engineText = Get-Content -LiteralPath $engineTarget -Raw
if (-not $engineText.Contains('[/Script/Engine.DataDrivenConsoleVariableSettings]')) {
    Add-Content -LiteralPath $engineTarget -Value ($engineLines[$sectionStart..($sectionEnd - 1)] -join [Environment]::NewLine) -Encoding utf8
}
$assetManagerRule = @'
[/Script/Engine.AssetManagerSettings]
+PrimaryAssetTypesToScan=(PrimaryAssetType="GameFeatureData",AssetBaseClass="/Script/GameFeatures.GameFeatureData",bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=,SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=AlwaysCook))
'@
if (-not (Test-Path -LiteralPath $gameTarget) -or -not (Select-String -LiteralPath $gameTarget -Pattern 'PrimaryAssetType="GameFeatureData"' -Quiet)) {
    Add-Content -LiteralPath $gameTarget -Value $assetManagerRule -Encoding utf8
}

$existingBridge = Get-Item -LiteralPath $bridgeLink -Force -ErrorAction SilentlyContinue
if ($existingBridge) {
    if ($existingBridge.LinkType -ne 'Junction' -or
        [IO.Path]::GetFullPath([string]$existingBridge.Target) -ne [IO.Path]::GetFullPath($bridgeSource)) {
        throw "The host bridge path already points elsewhere: $bridgeLink"
    }
} else {
    New-Item -ItemType Junction -Path $bridgeLink -Target $bridgeSource | Out-Null
}

$existing = Get-Item -LiteralPath $pluginLink -Force -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.LinkType -eq 'Junction') {
        if ([IO.Path]::GetFullPath([string]$existing.Target) -ne [IO.Path]::GetFullPath($pluginSource) -or
            -not [IO.Path]::GetFullPath($pluginLink).StartsWith([IO.Path]::GetFullPath($hostRoot) + [IO.Path]::DirectorySeparatorChar)) {
            throw "The host plugin path is not the expected local junction: $pluginLink"
        }
        Remove-Item -LiteralPath $pluginLink -Force
        $existing = $null
    } elseif ($existing.LinkType -or -not (Test-Path -LiteralPath (Join-Path $pluginLink 'MotionMatchingInCpp.uplugin'))) {
        throw "The host plugin path is not a complete local plugin copy: $pluginLink"
    }
}
if (-not $existing) {
    New-Item -ItemType Directory -Path $pluginLink | Out-Null
    foreach ($name in @('Config', 'Content', 'Resources', 'Source', 'MotionMatchingInCpp.uplugin', 'PORTABILITY.md')) {
        $item = Join-Path $pluginSource $name
        if (Test-Path -LiteralPath $item) {
            Copy-Item -LiteralPath $item -Destination $pluginLink -Recurse -Force
        }
    }
}
$helperHeader = Join-Path $pluginLink 'Source\MotionMatchingInCpp\CommonGameplay\Player\Data\BlueprintFunctionLibrary_MotionMatchingHelpers.h'
$helperText = [IO.File]::ReadAllText($helperHeader)
if ($helperText.Contains('FLinearColor Color;')) {
    [IO.File]::WriteAllText($helperHeader,
        $helperText.Replace('FLinearColor Color;', 'FLinearColor Color = FLinearColor::White;'),
        [Text.UTF8Encoding]::new($false))
} elseif (-not $helperText.Contains('FLinearColor Color = FLinearColor::White;')) {
    throw "The copied plugin helper header changed unexpectedly: $helperHeader"
}

$project = Get-Content -LiteralPath $projectPath -Raw | ConvertFrom-Json
if (-not @($project.Plugins | Where-Object { $_.Name -eq 'MotionMatchingInCpp' }).Count) {
    $project.Plugins = @($project.Plugins) + @([pscustomobject]@{ Name = 'MotionMatchingInCpp'; Enabled = $true })
    $project | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $projectPath -Encoding utf8
}
if (-not @($project.Plugins | Where-Object { $_.Name -eq 'AIAnimationMotionMatching' }).Count) {
    $project.Plugins = @($project.Plugins) + @([pscustomobject]@{ Name = 'AIAnimationMotionMatching'; Enabled = $true })
    $project | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $projectPath -Encoding utf8
}

Write-Output "MotionMatchingInCpp host plugin copy: $pluginLink"
Write-Output "AIAnimationMotionMatching host plugin: $bridgeLink"
Write-Output "Host project: $projectPath"
Write-Output "Host gameplay tags: $tagTarget"
