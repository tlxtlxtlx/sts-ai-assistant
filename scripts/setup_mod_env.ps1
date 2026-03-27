param(
    [string]$GameDir = "",
    [string]$BaseModJar = "",
    [string]$ModTheSpireJar = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$VendorDir = Join-Path $Root "vendor\slay-the-spire"
$GradleHome = Join-Path $Root ".gradle"
New-Item -ItemType Directory -Force $VendorDir | Out-Null
New-Item -ItemType Directory -Force $GradleHome | Out-Null

if (-not $GameDir) {
    $defaultSteam = "C:\Program Files (x86)\Steam\steamapps\common\SlayTheSpire"
    if (Test-Path $defaultSteam) {
        $GameDir = $defaultSteam
    }
}

if ($GameDir -and (Test-Path $GameDir)) {
    $desktopJar = Get-ChildItem -Path $GameDir -Filter "desktop-*.jar" | Select-Object -First 1
    if ($desktopJar) {
        Copy-Item $desktopJar.FullName (Join-Path $VendorDir $desktopJar.Name) -Force
    }
}

if ($BaseModJar -and (Test-Path $BaseModJar)) {
    Copy-Item $BaseModJar (Join-Path $VendorDir "BaseMod.jar") -Force
}

if ($ModTheSpireJar -and (Test-Path $ModTheSpireJar)) {
    Copy-Item $ModTheSpireJar (Join-Path $VendorDir "ModTheSpire.jar") -Force
}

$desktopVendor = Get-ChildItem -Path $VendorDir -Filter "desktop-*.jar" | Select-Object -First 1
if (-not $desktopVendor) {
    throw "No desktop-*.jar found under $VendorDir. Please pass -GameDir or copy the game jar manually."
}

$localProps = @()
$localProps += "sts.jar=../vendor/slay-the-spire/$($desktopVendor.Name)"
$localProps += "basemod.jar=../vendor/slay-the-spire/BaseMod.jar"
$localProps += "modthespire.jar=../vendor/slay-the-spire/ModTheSpire.jar"
[System.IO.File]::WriteAllLines((Join-Path $Root "mod\local.properties"), $localProps, [System.Text.UTF8Encoding]::new($false))

Write-Output "Vendor directory: $VendorDir"
Write-Output "GRADLE_USER_HOME should be: $GradleHome"
Write-Output "Generated mod/local.properties"
