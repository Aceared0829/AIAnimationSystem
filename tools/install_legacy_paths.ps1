# Restore local checkpoint paths after moving this repository's large artifacts.
$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$aliases = @{
    'motionbricks/unreal_data' = 'data/prepared'
    'motionbricks/unreal_runs' = 'training/runs'
    'motionbricks/out' = 'model-weight/base/motionbricks'
    'motionbricks/assets' = 'inference/assets'
}
foreach ($entry in $aliases.GetEnumerator()) {
    $aliasPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $entry.Key))
    $targetPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $entry.Value))
    if (!$aliasPath.StartsWith($repositoryRoot + [IO.Path]::DirectorySeparatorChar) -or !$targetPath.StartsWith($repositoryRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw 'Compatibility path escaped the repository.'
    }
    if (!(Test-Path -LiteralPath $targetPath -PathType Container)) { continue }
    if (Test-Path -LiteralPath $aliasPath) {
        $existing = Get-Item -LiteralPath $aliasPath -Force
        if ($existing.LinkType -ne 'Junction' -or [IO.Path]::GetFullPath($existing.Target) -ne $targetPath) {
            throw "Existing path is not the expected compatibility junction: $aliasPath"
        }
        continue
    }
    New-Item -ItemType Junction -Path $aliasPath -Target $targetPath | Select-Object FullName, Target
}
