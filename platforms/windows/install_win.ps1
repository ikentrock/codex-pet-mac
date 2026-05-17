$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $HOME ".local\bin"
$VenvDir = Join-Path $HOME ".local\share\deskpet\venv"
$Launcher = Join-Path $InstallDir "deskpet.cmd"

Write-Host "=== DeskPet Windows — installer ==="
Write-Host ""

$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) {
    $PythonCmd = @("py", "-3")
} else {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $Python) {
        throw "Python 3.10+ is required. Install it from https://www.python.org/downloads/windows/"
    }
    $PythonCmd = @("python")
}

function Invoke-SelectedPython {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    if ($PythonCmd.Length -gt 1) {
        & $PythonCmd[0] @($PythonCmd[1..($PythonCmd.Length - 1)]) @Arguments
    } else {
        & $PythonCmd[0] @Arguments
    }
}

$Version = Invoke-SelectedPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$Parts = $Version.Split(".")
if ([int]$Parts[0] -lt 3 -or ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -lt 10)) {
    throw "Python 3.10+ is required. Found Python $Version."
}

Write-Host "Using Python $Version"

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv: $VenvDir"
    Invoke-SelectedPython -m venv $VenvDir
} else {
    Write-Host "Venv exists: $VenvDir"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

Write-Host "Installing dependencies..."
& $VenvPip install -r (Join-Path $PSScriptRoot "requirements.txt")

New-Item -ItemType Directory -Force -Path (Join-Path $HOME "pets") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $HOME ".deskpet\pets") | Out-Null

# Copy bundled pets from the repo's pets/ directory (skip if already present)
$RepoPets = Join-Path $PSScriptRoot "..\..\pets"
if (Test-Path $RepoPets) {
    Get-ChildItem -Path $RepoPets -Filter "*-pet.zip" | ForEach-Object {
        $dst = Join-Path $HOME "pets\$($_.Name)"
        if (-not (Test-Path $dst)) {
            Copy-Item $_.FullName -Destination $dst
            Write-Host "  Installed pet: $($_.Name)"
        }
    }
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$ScriptPath = Join-Path $PSScriptRoot "desktop_pet.py"
$LauncherContent = @"
@echo off
"$VenvPython" "$ScriptPath" %*
"@
Set-Content -Path $Launcher -Value $LauncherContent -Encoding ASCII

Write-Host ""
Write-Host "Installed: $Launcher"
Write-Host "Pets libraries:"
Write-Host "  $HOME\pets"
Write-Host "  $HOME\.deskpet\pets"
Write-Host ""
Write-Host "Run with:"
Write-Host "  $Launcher"
Write-Host ""
Write-Host "Tip: add $InstallDir to your PATH if you want to run deskpet from any terminal."
