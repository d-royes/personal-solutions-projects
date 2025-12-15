# PowerShell script to reset the frontend server (kill hung processes + restart)

param (
    [string]$Port = "5173"
)

$ErrorActionPreference = "Stop"

# Get paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptDir  # daily-task-assistant
$projectsDir = Split-Path -Parent $backendPath  # projects
$frontendPath = Join-Path $projectsDir "web-dashboard"

Write-Host "Resetting frontend server on port $Port..." -ForegroundColor Cyan

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

# Note: We intentionally do NOT kill all background Node processes here.
# Claude Code CLI and other tools run on Node.js - killing them would disrupt the session.
# The Stop-PortProcess function above handles the specific Vite dev server.

Write-Host "Starting frontend..." -ForegroundColor Cyan

# Build and run the frontend command in a new window
$frontendCmd = @"
Set-Location '$frontendPath'
npm run dev -- --host 0.0.0.0 --port $Port
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

Write-Host "Frontend started: http://localhost:$Port" -ForegroundColor Green
