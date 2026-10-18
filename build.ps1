# 一键构建：建 venv -> 装依赖 -> 生成图标 -> 打包
# 用法： powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$env:TMP = Join-Path $root ".tmp"
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Force -Path $env:TMP | Out-Null

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "== 创建虚拟环境 ==" -ForegroundColor Cyan
    py -3.13 -m venv .venv
}

Write-Host "== 安装依赖 ==" -ForegroundColor Cyan
& $py -m pip install --no-cache-dir --upgrade pip
& $py -m pip install --no-cache-dir numpy bettercam mss PySide6 pyinstaller

Write-Host "== 生成图标 ==" -ForegroundColor Cyan
& $py tools\gen_icon.py

Write-Host "== 打包 ==" -ForegroundColor Cyan
& $py -m PyInstaller --noconfirm --clean lonGon-AutoQTE-Tool.spec

$src = Join-Path $root "dist\lonGon-AutoQTE-Tool"
$dst = Join-Path $root "lonGon-AutoQTE-Tool"

Write-Host "== 复制到发布文件夹 ==" -ForegroundColor Cyan
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item (Join-Path $src "*") $dst -Recurse -Force
Copy-Item (Join-Path $root "packaging\使用说明.txt") $dst -Force

$out = Join-Path $dst "lonGon-AutoQTE-Tool.exe"
if (Test-Path $out) {
    $size = [math]::Round((Get-ChildItem $dst -Recurse |
        Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "== 完成：$out  (总 $size MB) ==" -ForegroundColor Green
} else {
    Write-Host "!! 打包失败，看 build\pyi.log" -ForegroundColor Red
    exit 1
}

# ---- 生成发布用的 zip + 校验值 ----
$ver = (Select-String -Path (Join-Path $root "src\longon_qte\__init__.py") `
        -Pattern 'APP_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$pub = Join-Path $root "发布"
New-Item -ItemType Directory -Force -Path $pub | Out-Null
Copy-Item (Join-Path $root "docs\screenshot.png") (Join-Path $pub "截图.png") -Force

$zip = Join-Path $pub "lonGon-AutoQTE-Tool-v$ver-win64.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $dst, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $false)
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
"$hash  $(Split-Path $zip -Leaf)" | Set-Content (Join-Path $pub "SHA256.txt") -Encoding ASCII

Write-Host ("== 发布包：{0}  ({1:N1} MB) ==" -f $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
Write-Host "   SHA256: $hash" -ForegroundColor DarkGray
Write-Host "   上传到 GitHub Release 的就是这个 zip 和 SHA256.txt" -ForegroundColor Green
