#Requires -Version 5.1
$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$VenvDir = ".venv"
$EnvFile = ".env"
$MinPyMajor = 3
$MinPyMinor = 8

function Info($msg)  { Write-Host "[setup] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[setup] $msg" -ForegroundColor Yellow }
function ErrorMsg($msg) { Write-Host "[setup] $msg" -ForegroundColor Red }

# -- 1. Python -----------------------------------------------------------------
function Test-PythonCmd {
    foreach ($cmd in @("python", "py")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            return $cmd
        }
    }
    return $null
}

function Install-Python {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Info "Installing/upgrading Python via winget..."
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    } else {
        ErrorMsg "winget not found. Cannot install Python automatically. Install Python $MinPyMajor.$MinPyMinor+ manually: https://python.org/downloads"
        exit 1
    }
}

function Test-VersionOk($cmd) {
    $maj = & $cmd -c "import sys; print(sys.version_info.major)"
    $min = & $cmd -c "import sys; print(sys.version_info.minor)"
    return ([int]$maj -gt $MinPyMajor) -or (([int]$maj -eq $MinPyMajor) -and ([int]$min -ge $MinPyMinor))
}

$PyCmd = Test-PythonCmd

if (-not $PyCmd) {
    Warn "Python not found."
    Install-Python
    $PyCmd = Test-PythonCmd
    if (-not $PyCmd) {
        ErrorMsg "Python install failed — python/py still not on PATH. Restart shell and re-run setup, or install manually: https://python.org/downloads"
        exit 1
    }
} elseif (-not (Test-VersionOk $PyCmd)) {
    $PyMajor = & $PyCmd -c "import sys; print(sys.version_info.major)"
    $PyMinor = & $PyCmd -c "import sys; print(sys.version_info.minor)"
    Warn "Python $PyMajor.$PyMinor too old (need $MinPyMajor.$MinPyMinor+). Upgrading automatically..."
    Install-Python
    $PyCmd = Test-PythonCmd
}

if (-not (Test-VersionOk $PyCmd)) {
    $PyMajor = & $PyCmd -c "import sys; print(sys.version_info.major)"
    $PyMinor = & $PyCmd -c "import sys; print(sys.version_info.minor)"
    ErrorMsg "Auto-upgrade failed — still $PyMajor.$PyMinor, need $MinPyMajor.$MinPyMinor+."
    exit 1
}

$PyMajor = & $PyCmd -c "import sys; print(sys.version_info.major)"
$PyMinor = & $PyCmd -c "import sys; print(sys.version_info.minor)"
Info "Python $PyMajor.$PyMinor OK."

# -- 2. Virtualenv --------------------------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Info "Creating virtual environment..."
    & $PyCmd -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Activate = Join-Path $VenvDir "Scripts\Activate.ps1"
. $Activate
Info "Virtualenv activated."

# -- 3. Dependencies -------------------------------------------------------------
Info "Installing dependencies..."
& $VenvPython -m pip install --upgrade pip -q
& $VenvPython -m pip install -r requirements.txt -q
Info "Dependencies installed."

# -- 4. .env setup ----------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Info "No .env found - running first-time setup."

    Write-Host ""
    Write-Host "  Get a bot token from @BotFather on Telegram."
    $BotToken = Read-Host "  Enter BOT_TOKEN"
    if ([string]::IsNullOrWhiteSpace($BotToken)) {
        ErrorMsg "BOT_TOKEN cannot be empty."
        exit 1
    }

    Info "Generating encryption key..."
    $EncryptionKey = & $VenvPython -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    @"
BOT_TOKEN=$BotToken
ENCRYPTION_KEY=$EncryptionKey
EDIT_INTERVAL=5
"@ | Set-Content -Path $EnvFile -Encoding utf8NoBOM

    Info ".env written. Keep it safe - it holds your encryption key."
    Write-Host ""
} else {
    Info ".env already exists - skipping setup."
}

# -- 5. Run -----------------------------------------------------------------------
Info "Starting bot..."
Write-Host ""
& $VenvPython bot.py
