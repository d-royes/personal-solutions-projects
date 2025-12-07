# PowerShell script to start Daily Task Assistant backend + frontend locally.

param (
    [string]$BackendPort = "8000",
    [string]$FrontendPort = "5173"
)

$ErrorActionPreference = "Stop"

# Script is at: projects/daily-task-assistant/scripts/start-dev.ps1
# Go up 3 levels to get repo root: scripts -> daily-task-assistant -> projects -> repo root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptDir  # daily-task-assistant
$projectsDir = Split-Path -Parent $backendPath  # projects
$repoRoot = Split-Path -Parent $projectsDir  # repo root
$frontendPath = Join-Path $projectsDir "web-dashboard"

Write-Host "Starting backend from $backendPath..." -ForegroundColor Cyan

# Load .env file and build environment variable assignments for the subprocess
$envFile = Join-Path $backendPath ".env"
$envSetters = @()
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            $varName = $Matches[1]
            $varValue = $Matches[2]
            # Escape single quotes in values
            $escapedValue = $varValue -replace "'", "''"
            $envSetters += "`$env:$varName = '$escapedValue'"
        }
    }
}

$envBlock = ($envSetters -join "; ") + "; "

# Build the full command
$backendCmd = @"
Set-Location '$backendPath'
`$env:PYTHONPATH = '.'
`$env:DTA_DEV_AUTH_BYPASS = '1'
$envBlock
python -m uvicorn api.main:app --host 0.0.0.0 --port $BackendPort
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

Write-Host "Starting frontend from $frontendPath..." -ForegroundColor Cyan

$frontendCmd = @"
Set-Location '$frontendPath'
npm install
npm run dev -- --host 0.0.0.0 --port $FrontendPort
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

Write-Host "Backend: http://localhost:$BackendPort  |  Frontend: http://localhost:$FrontendPort"
