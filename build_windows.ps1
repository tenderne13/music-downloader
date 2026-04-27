param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir",
    [string]$Icon = ""
)

$ErrorActionPreference = "Stop"
$defaultIcon = "assets/icons/app_icon.ico"

if (-not $Icon -and (Test-Path $defaultIcon)) {
    $Icon = $defaultIcon
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Missing .venv\\Scripts\\python.exe. Create the virtual environment and install dependencies first."
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
& .\.venv\Scripts\python.exe -m playwright install chromium

$buildArgs = @("build_release.py", $Mode)
if ($Icon) {
    $buildArgs += @("--icon", $Icon)
}

& .\.venv\Scripts\python.exe @buildArgs
