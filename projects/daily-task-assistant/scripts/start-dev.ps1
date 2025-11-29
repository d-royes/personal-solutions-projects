# PowerShell script to start Daily Task Assistant backend + frontend locally.

param (
    [string]$BackendPort = "8000",
    [string]$FrontendPort = "5173"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backendPath = Join-Path $repoRoot "projects\daily-task-assistant"
$frontendPath = Join-Path $repoRoot "projects\web-dashboard"

Write-Host "Starting backend from $backendPath..." -ForegroundColor Cyan

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$backendPath`"; `$$env:PYTHONPATH='.'; `$$env:DTA_DEV_AUTH_BYPASS='1'; python -m uvicorn api.main:app --host 0.0.0.0 --port $BackendPort"
) -WindowStyle Normal

Write-Host "Starting frontend from $frontendPath..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$frontendPath`"; npm install; npm run dev -- --host 0.0.0.0 --port $FrontendPort"
) -WindowStyle Normal

Write-Host "Backend: http://localhost:$BackendPort  |  Frontend: http://localhost:$FrontendPort"

