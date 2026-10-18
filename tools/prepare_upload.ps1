# 生成"上传到仓库"文件夹：只挑该进 GitHub 的文件，方便网页拖拽上传
# 用法： powershell -ExecutionPolicy Bypass -File .\tools\prepare_upload.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$dst = Join-Path $root "上传到仓库"

$skipDirs = @(".venv", "build", "dist", "release", "发布", "上传到仓库",
              "lonGon-AutoQTE-Tool", ".git", ".tmp", "__pycache__")

if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dst | Out-Null

$count = 0
Get-ChildItem $root -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($root.Length + 1)
    $top = ($rel -split "\\")[0]
    if ($skipDirs -contains $top) { return }
    if ($rel -match "__pycache__") { return }
    if ($_.Name -eq "lonGon-AutoQTE-Tool.json") { return }
    if ($_.Extension -eq ".log") { return }

    $target = Join-Path $dst $rel
    $dir = Split-Path $target
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item $_.FullName $target -Force
    $count++
}

$size = [math]::Round((Get-ChildItem $dst -Recurse -File | Measure-Object Length -Sum).Sum / 1KB, 0)
Write-Host "== 已生成：$dst ==" -ForegroundColor Green
Write-Host "   $count 个文件，共 $size KB" -ForegroundColor Green
Write-Host "   打开这个文件夹，全选（Ctrl+A）后拖进 GitHub 网页的上传框即可" -ForegroundColor Gray
