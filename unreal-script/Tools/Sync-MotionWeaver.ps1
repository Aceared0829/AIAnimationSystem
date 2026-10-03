[CmdletBinding(SupportsShouldProcess)]
param(
	[switch]$Check
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$sourceRoot = Join-Path $repositoryRoot 'unreal-sample\UMWSamplePreview\Plugins\MotionWeaver'
$mirrorRoot = Join-Path $repositoryRoot 'unreal-script\MotionWeaver'
$excludedDirectories = @('Binaries', 'Intermediate', 'Saved')

if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
	throw "MotionWeaver 源插件不存在：$sourceRoot"
}

function Get-RelativePath([string]$Root, [string]$Path)
{
	return $Path.Substring($Root.Length).TrimStart('\', '/')
}

function Test-IsExcludedPath([string]$RelativePath)
{
	$segments = $RelativePath -split '[\\/]'
	return [bool]($segments | Where-Object { $excludedDirectories -contains $_ })
}

$sourceFiles = @(
	Get-ChildItem -LiteralPath $sourceRoot -File -Recurse |
		Where-Object {
			$relativePath = Get-RelativePath $sourceRoot $_.FullName
			-not (Test-IsExcludedPath $relativePath)
		}
)

$sourceByRelativePath = @{}
foreach ($sourceFile in $sourceFiles) {
	$relativePath = Get-RelativePath $sourceRoot $sourceFile.FullName
	$sourceByRelativePath[$relativePath] = $sourceFile
}

$mirrorFiles = @()
if (Test-Path -LiteralPath $mirrorRoot -PathType Container) {
	$mirrorFiles = @(
		Get-ChildItem -LiteralPath $mirrorRoot -File -Recurse |
			Where-Object {
				$relativePath = Get-RelativePath $mirrorRoot $_.FullName
				-not (Test-IsExcludedPath $relativePath)
			}
	)
}

$mismatches = [System.Collections.Generic.List[string]]::new()
foreach ($sourceFile in $sourceFiles) {
	$relativePath = Get-RelativePath $sourceRoot $sourceFile.FullName
	$mirrorPath = Join-Path $mirrorRoot $relativePath
	if (-not (Test-Path -LiteralPath $mirrorPath -PathType Leaf)) {
		$mismatches.Add("缺少 $relativePath")
		continue
	}

	$sourceHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
	$mirrorHash = (Get-FileHash -LiteralPath $mirrorPath -Algorithm SHA256).Hash
	if ($sourceHash -ne $mirrorHash) {
		$mismatches.Add("内容不同 $relativePath")
	}
}

foreach ($mirrorFile in $mirrorFiles) {
	$relativePath = Get-RelativePath $mirrorRoot $mirrorFile.FullName
	if (-not $sourceByRelativePath.ContainsKey($relativePath)) {
		$mismatches.Add("镜像多出 $relativePath")
	}
}

if ($Check) {
	if ($mismatches.Count -gt 0) {
		$mismatches | ForEach-Object { Write-Error $_ }
		throw 'MotionWeaver 镜像未同步。'
	}

	Write-Output "MotionWeaver 镜像已同步：$mirrorRoot"
	return
}

foreach ($sourceFile in $sourceFiles) {
	$relativePath = Get-RelativePath $sourceRoot $sourceFile.FullName
	$mirrorPath = Join-Path $mirrorRoot $relativePath
	$mirrorDirectory = Split-Path -Parent $mirrorPath
	if (-not (Test-Path -LiteralPath $mirrorDirectory -PathType Container)) {
		if ($PSCmdlet.ShouldProcess($mirrorDirectory, '创建镜像目录')) {
			New-Item -ItemType Directory -Path $mirrorDirectory -Force | Out-Null
		}
	}

	if ($PSCmdlet.ShouldProcess($mirrorPath, '从 Sample 插件复制')) {
		Copy-Item -LiteralPath $sourceFile.FullName -Destination $mirrorPath -Force
	}
}

foreach ($mirrorFile in $mirrorFiles) {
	$relativePath = Get-RelativePath $mirrorRoot $mirrorFile.FullName
	if (-not $sourceByRelativePath.ContainsKey($relativePath) -and
		$PSCmdlet.ShouldProcess($mirrorFile.FullName, '删除过期镜像文件')) {
		Remove-Item -LiteralPath $mirrorFile.FullName -Force
	}
}

if (Test-Path -LiteralPath $mirrorRoot -PathType Container) {
	Get-ChildItem -LiteralPath $mirrorRoot -Directory -Recurse |
		Sort-Object FullName -Descending |
		Where-Object { @(Get-ChildItem -LiteralPath $_.FullName -Force).Count -eq 0 } |
		ForEach-Object {
			if ($PSCmdlet.ShouldProcess($_.FullName, '删除空的过期镜像目录')) {
				Remove-Item -LiteralPath $_.FullName -Force
			}
		}
}

Write-Output "MotionWeaver 已从 Sample 同步到：$mirrorRoot"
