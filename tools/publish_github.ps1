# 用 GitHub API 一键发布（不需要装 Git/gh，只需要一个 classic token）
#
# 1) 打开 https://github.com/settings/tokens/new
#    勾选 repo（整块），生成后复制那串 ghp_ 开头的
# 2) 在 PowerShell 里：
#    $env:GH_TOKEN = "ghp_你的token"
#    powershell -ExecutionPolicy Bypass -File .\tools\publish_github.ps1
#
# 可选参数：
#    -Private              建成私有仓库
#    -NoRelease            只推代码，不发 Release
#    -Repo my-name         换仓库名
#    -Tag v1.0.0           换 tag
#
param(
    [string]$Token = $env:GH_TOKEN,
    [string]$Repo = "lonGon-AutoQTE-Tool",
    [string]$Description = "给自己游戏写的自动QTE工具，截屏认白区，到点按空格。不读内存，不注入进程。",
    [string]$Tag = "v1.0.0",
    [string]$SrcDir = "",
    [string]$Zip = "",
    [switch]$Private,
    [switch]$NoRelease
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
if (-not $SrcDir) { $SrcDir = Join-Path $root "上传到仓库" }
if (-not $Zip)    { $Zip = Join-Path $root "发布\lonGon-AutoQTE-Tool-$Tag-win64.zip" }

if (-not $Token) {
    Write-Host "缺少 token。先执行： `$env:GH_TOKEN = `"ghp_...`"" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $SrcDir)) { Write-Host "找不到源码目录：$SrcDir" -ForegroundColor Red; exit 1 }

$Headers = @{
    Authorization = "token $Token"
    "User-Agent" = "lonGon-publish"
    Accept = "application/vnd.github+json"
}

function Api {
    param([string]$Method, [string]$Url, $Body)
    if ($null -ne $Body) {
        $json = $Body | ConvertTo-Json -Depth 12 -Compress
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        return Invoke-RestMethod -Method $Method -Uri $Url -Headers $Headers `
            -Body $bytes -ContentType "application/json; charset=utf-8" -TimeoutSec 120
    }
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $Headers -TimeoutSec 120
}

# ---------- 1. 我是谁 ----------
try {
    $me = Api GET "https://api.github.com/user" $null
} catch {
    Write-Host "token 无效或没权限：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
$owner = $me.login
Write-Host "== 登录身份：$owner ==" -ForegroundColor Cyan

# ---------- 2. 建仓库（已存在就复用）----------
$base = "https://api.github.com/repos/$owner/$Repo"
$repoExists = $true
try {
    $repo = Api GET $base $null
} catch {
    $repoExists = $false
}

if (-not $repoExists) {
    Write-Host "== 创建仓库 $owner/$Repo ==" -ForegroundColor Cyan
    $repo = Api POST "https://api.github.com/user/repos" @{
        name = $Repo
        description = $Description
        private = [bool]$Private
        has_issues = $true
        has_wiki = $false
        auto_init = $false
    }
} else {
    Write-Host "== 仓库已存在，将作为一次新提交推上去 ==" -ForegroundColor Yellow
    Api PATCH $base @{ description = $Description } | Out-Null
}

# ---------- 3. 把文件做成一次提交 ----------
$files = Get-ChildItem $SrcDir -Recurse -File -Force
Write-Host ("== 上传 {0} 个文件 ==" -f $files.Count) -ForegroundColor Cyan

$treeEntries = @()
$i = 0
foreach ($f in $files) {
    $rel = $f.FullName.Substring($SrcDir.Length + 1).Replace("\", "/")
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($f.FullName))
    $blob = Api POST "$base/git/blobs" @{ content = $b64; encoding = "base64" }
    $treeEntries += @{ path = $rel; mode = "100644"; type = "blob"; sha = $blob.sha }
    $i++
    if ($i % 10 -eq 0) { Write-Host ("   ... {0}/{1}" -f $i, $files.Count) -ForegroundColor DarkGray }
}

$parents = @()
$baseTree = $null
try {
    $head = Api GET "$base/git/ref/heads/main" $null
    $parents = @($head.object.sha)
    $headCommit = Api GET "$base/git/commits/$($head.object.sha)" $null
    $baseTree = $headCommit.tree.sha
} catch { }

$treeBody = @{ tree = $treeEntries }
if ($baseTree) { $treeBody.base_tree = $baseTree }
$tree = Api POST "$base/git/trees" $treeBody

$commitBody = @{ message = "lonGon-AutoQTE-Tool $Tag"; tree = $tree.sha; parents = $parents }
$commit = Api POST "$base/git/commits" $commitBody

if ($parents.Count -gt 0) {
    Api PATCH "$base/git/refs/heads/main" @{ sha = $commit.sha; force = $true } | Out-Null
} else {
    Api POST "$base/git/refs" @{ ref = "refs/heads/main"; sha = $commit.sha } | Out-Null
}
Api PATCH $base @{ default_branch = "main" } | Out-Null
Write-Host "== 代码已推送 ==" -ForegroundColor Green

# ---------- 4. Topics ----------
try {
    Api PUT "$base/topics" @{ names = @("qte", "game-tool", "computer-vision", "pyqt6", "dxgi", "windows") } | Out-Null
} catch { Write-Host "topics 设置失败（不影响发布）" -ForegroundColor DarkYellow }

# ---------- 5. Release ----------
if (-not $NoRelease) {
    if (-not (Test-Path $Zip)) {
        Write-Host "找不到 zip：$Zip（跳过 Release）" -ForegroundColor Yellow
    } else {
        Write-Host "== 创建 Release $Tag ==" -ForegroundColor Cyan
        $notes = @"
## 下载

- ``$(Split-Path $Zip -Leaf)``（Windows 10/11 x64）
- 解压到任意目录，双击 ``lonGon-AutoQTE-Tool.exe``
- 不需要安装 Python，不需要管理员权限，不联网

## 本次更新

- 单帧处理：截图 1.5ms + 推理 0.7ms（RTX 4060 Laptop / 2560×1440）
- 连打加速自适应、OBS 纯净预览窗、滚轮防误触

## 注意

- 仅用于 lonGon 自制的单机游戏，不支持任何反作弊绕过。
- 程序未签名，首次运行如遇 SmartScreen 提示，点「更多信息 → 仍要运行」。
"@
        $rel = Api POST "$base/releases" @{
            tag_name = $Tag
            target_commitish = "main"
            name = "lonGon-AutoQTE-Tool $Tag"
            body = $notes
        }

        $uploadBase = "https://uploads.github.com/repos/$owner/$Repo/releases/$($rel.id)/assets"
        Write-Host ("== 上传附件 {0} ({1:N1} MB) ==" -f (Split-Path $Zip -Leaf), ((Get-Item $Zip).Length / 1MB)) -ForegroundColor Cyan
        Invoke-RestMethod -Method Post -Uri "$uploadBase?name=$([uri]::EscapeDataString((Split-Path $Zip -Leaf)))" `
            -Headers $Headers -InFile $Zip -ContentType "application/octet-stream" -TimeoutSec 1800 | Out-Null

        $sha = Join-Path (Split-Path $Zip) "SHA256.txt"
        if (Test-Path $sha) {
            Invoke-RestMethod -Method Post -Uri "$uploadBase?name=SHA256.txt" `
                -Headers $Headers -InFile $sha -ContentType "text/plain" -TimeoutSec 120 | Out-Null
        }
        Write-Host "== Release 完成 ==" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "仓库： https://github.com/$owner/$Repo" -ForegroundColor Green
Write-Host "下载页：https://github.com/$owner/$Repo/releases" -ForegroundColor Green
