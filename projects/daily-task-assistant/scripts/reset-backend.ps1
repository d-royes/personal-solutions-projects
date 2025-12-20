# PowerShell script to reset the backend server (kill hung processes + restart)

param (
    [string]$Port = "8000"
)

$ErrorActionPreference = "Stop"

# Get paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptDir  # daily-task-assistant

Write-Host "Resetting backend server on port $Port..." -ForegroundColor Cyan

# Kill any processes on the port (including orphaned uvicorn children)
function Stop-PortProcess {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        Write-Host "  No existing process on port $Port" -ForegroundColor Gray
        return
    }
    $processIds = $connections.OwningProcess | Select-Object -Unique
    $orphanedParents = @()

    foreach ($procId in $processIds) {
        # Skip PID 0 (Windows Idle process)
        if ($procId -eq 0) { continue }

        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                Write-Host "  Stopping $($proc.ProcessName) (PID $procId)..." -ForegroundColor Yellow
                Stop-Process -Id $procId -Force
            } else {
                # Parent process is dead but port still held - collect for orphan cleanup
                $orphanedParents += $procId
                Write-Host "  Parent PID $procId is dead (zombie)" -ForegroundColor DarkYellow
            }
        } catch {
            $orphanedParents += $procId
            Write-Host "  Parent PID $procId not found (zombie)" -ForegroundColor DarkYellow
        }
    }

    # Kill orphaned child processes (uvicorn children whose parents died)
    if ($orphanedParents.Count -gt 0) {
        Write-Host "  Hunting orphaned uvicorn children..." -ForegroundColor Yellow
        $orphans = Get-CimInstance Win32_Process | Where-Object {
            $_.ParentProcessId -in $orphanedParents -and $_.Name -match 'python'
        }
        foreach ($orphan in $orphans) {
            try {
                Write-Host "  Killing orphan $($orphan.Name) (PID $($orphan.ProcessId), parent was $($orphan.ParentProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $orphan.ProcessId -Force
            } catch {
                Write-Warning ("  Failed to kill orphan PID {0}: {1}" -f $orphan.ProcessId, $_)
            }
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
