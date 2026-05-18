param(
    [switch]$InstallPyInstaller,
    [switch]$InstallDeps,
    [switch]$OneDir,
    [switch]$UseCurrentPython
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$ErrorActionPreference = "Continue"

$PythonExe = "python"
if (-not $UseCurrentPython) {
    $VenvPython = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        python -m venv ".venv-build"
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    $PythonExe = $VenvPython
}

$requirementsPath = Join-Path $PSScriptRoot "requirements-gui.txt"
$frontendPath = Join-Path $PSScriptRoot "frontend"
$frontendModulesPath = Join-Path $frontendPath "node_modules"
$frontendDistPath = Join-Path $frontendPath "dist"

& $PythonExe -c "import PyInstaller, webview" *> $null
if ($LASTEXITCODE -ne 0) {
    if (-not ($InstallDeps -or $InstallPyInstaller)) {
        Write-Host "GUI build dependencies are missing. Run:"
        Write-Host "  .\build_exe.ps1 -InstallDeps"
        Write-Host "The dependency list is in requirements-gui.txt."
        exit 1
    }
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $PythonExe -m pip install --upgrade -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not (Test-Path $frontendModulesPath)) {
    if (-not ($InstallDeps -or $InstallPyInstaller)) {
        Write-Host "Frontend dependencies are missing. Run:"
        Write-Host "  .\build_exe.ps1 -InstallDeps"
        exit 1
    }
    Push-Location $frontendPath
    npm install
    $npmInstallCode = $LASTEXITCODE
    Pop-Location
    if ($npmInstallCode -ne 0) {
        exit $npmInstallCode
    }
} elseif ($InstallDeps -or $InstallPyInstaller) {
    Push-Location $frontendPath
    npm install
    $npmInstallCode = $LASTEXITCODE
    Pop-Location
    if ($npmInstallCode -ne 0) {
        exit $npmInstallCode
    }
}

Push-Location $frontendPath
npm run build
$npmBuildCode = $LASTEXITCODE
Pop-Location
if ($npmBuildCode -ne 0) {
    exit $npmBuildCode
}

$modeArg = if ($OneDir) { "--onedir" } else { "--onefile" }
$pyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    $modeArg,
    "--add-data",
    "$frontendDistPath;frontend\dist",
    "--name",
    "TxtToEpubConverter",
    "txt_to_epub_gui.py"
)

& $PythonExe -m PyInstaller @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($OneDir) {
    Write-Host "Built: dist\TxtToEpubConverter\TxtToEpubConverter.exe"
} else {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "dist\TxtToEpubConverter.exe") -Destination (Join-Path $PSScriptRoot "TxtToEpubConverter.exe") -Force
    Write-Host "Built: dist\TxtToEpubConverter.exe"
    Write-Host "Copied: TxtToEpubConverter.exe"
}
