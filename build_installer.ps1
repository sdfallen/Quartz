param(
    [Parameter(Mandatory=$true)][string]$PackageDir,
    [string]$Version = '2026.10.29',
    [string]$OutputDir
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$compilerPaths = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$compiler = $compilerPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    throw 'Inno Setup 6 bulunamadı. Önce Inno Setup derleyicisini kurun.'
}
$package = (Resolve-Path -LiteralPath $PackageDir).Path
if ($Version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') { throw 'Geçersiz sürüm.' }
if (-not $OutputDir) { $OutputDir = Join-Path $root "dist\releases\Quartz-$Version" }
$output = [System.IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath (Join-Path $output "QuartzSetup-$Version.exe")) { throw 'Mevcut setup üzerine yazılmaz.' }
$app = Join-Path $package 'Quartz.exe'
if (-not (Test-Path -LiteralPath $app)) {
    throw 'Quartz.exe bulunamadı. Önce build.py çalıştırılmalı.'
}
Push-Location -LiteralPath $root
try {
    & python -B scripts/audit_publish.py --package $package
    if ($LASTEXITCODE -ne 0) { throw 'Paket gizlilik denetimi başarısız.' }
    & python -B scripts/verify_desktop_package.py $app
    if ($LASTEXITCODE -ne 0) { throw 'Paket kaynak eşleşmesi başarısız.' }
    & $compiler "/DPackageDir=$package" "/DReleaseOutput=$output" "/DMyAppVersion=$Version" (Join-Path $root 'installer\Quartz.iss')
} finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Kurulum derlemesi başarısız: $LASTEXITCODE" }
Write-Host "Hazır: $output\QuartzSetup-$Version.exe"
