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
$app = Join-Path $root 'dist\Quartz\Quartz.exe'
if (-not (Test-Path -LiteralPath $app)) {
    throw 'Quartz.exe bulunamadı. Önce build.py çalıştırılmalı.'
}
& $compiler (Join-Path $root 'installer\Quartz.iss')
if ($LASTEXITCODE -ne 0) { throw "Kurulum derlemesi başarısız: $LASTEXITCODE" }
Write-Host "Hazır: $root\dist\installer\QuartzSetup-1.0.0.exe"
