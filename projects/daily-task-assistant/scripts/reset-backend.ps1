# PowerShell script to reset the backend server (kill hung processes + restart)

param (
    [string]$Port = "8000"
)

$ErrorActionPreference = "Stop"

# Get paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptDir  # daily-task-assistant

Write-Host "Resetting backend server on port $Port..." -ForegroundColor Cyan

# Kill any processes on the port
function Stop-PortProcess {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        Write-Host "  No existing process on port $Port" -ForegroundColor Gray
        return
    }
    $processIds = $connections.OwningProcess | Select-Object -Unique
    foreach ($procId in $processIds) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            Write-Host "  Stopping $($proc.ProcessName) (PID $procId)..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
        } catch {
            Write-Warning ("  Failed to stop PID {0}: {1}" -f $procId, $_)
        }
    }
    # Brief pause to ensure port is released
    Start-Sleep -Milliseconds 500
}

Stop-PortProcess -Port $Port

# Note: We intentionally do NOT kill all background Python processes here.
# Other tools and services may run on Python - killing them could disrupt workflows.
# The Stop-PortProcess function above handles the specific uvicorn dev server.

Write-Host "Starting backend..." -ForegroundColor Cyan

# Load .env file and build environment variable assignments
$envFile = Join-Path $backendPath ".env"
$envSetters = @()
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $varName = $Matches[1]
            $varValue = $Matches[2]
            $escapedValue = $varValue -replace "'", "''"
            $envSetters += "`$env:$varName = '$escapedValue'"
        }
    }
}

$envBlock = ($envSetters -join "; ") + "; "

# Build and run the backend command in a new window
$backendCmd = @"
Set-Location '$backendPath'
`$env:PYTHONPATH = '.'
`$env:DTA_DEV_AUTH_BYPASS = '1'
$envBlock
python -m uvicorn api.main:app --host 0.0.0.0 --port $Port --reload
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

Write-Host "Backend started: http://localhost:$Port" -ForegroundColor Green
