# PowerShell script to reset the backend server (kill hung processes + restart)
#
# CRITICAL: This script MUST be used after ANY backend code changes.
# uvicorn's --reload flag does NOT reliably kill child processes on Windows.
# Orphaned Python processes will serve OLD CODE even after the parent is killed.
#
# See: https://rolisz.ro/2024/fastapi-server-stuck-on-windows/
# See: https://github.com/Kludex/uvicorn/issues/2289

param (
    [string]$Port = "8000"
)

$ErrorActionPreference = "Continue"  # Don't stop on non-critical errors

# Get paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Split-Path -Parent $scriptDir  # daily-task-assistant

Write-Host "Resetting backend server on port $Port..." -ForegroundColor Cyan

function Stop-ProcessTree {
    <#
    .SYNOPSIS
    Kills a process and ALL its child processes using taskkill /T

    .DESCRIPTION
    On Windows, Stop-Process only kills the specified process, not its children.
    taskkill /T /F kills the entire process tree, which is essential for uvicorn
    which spawns worker processes that can become orphaned.
    #>
    param([int]$ProcessId)

    Write-Host "  Killing process tree for PID $ProcessId..." -ForegroundColor Yellow
    # /T = Kill process tree, /F = Force
    $result = & taskkill /PID $ProcessId /T /F 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Success: $result" -ForegroundColor Green
    } else {
        Write-Host "    Note: $result" -ForegroundColor Gray
    }
}

function Stop-PortProcesses {
    <#
    .SYNOPSIS
    Finds and kills ALL processes holding a port, including orphaned children

    .DESCRIPTION
    This function handles the Windows uvicorn zombie problem:
    1. Finds all PIDs holding the port via netstat
    2. Kills each process tree with taskkill /T
    3. Hunts for orphaned Python processes whose parents are dead
    4. Verifies port is clear before returning
    #>
    param([int]$Port)

    # Step 1: Get all PIDs holding the port
    Write-Host "  Scanning port $Port for processes..." -ForegroundColor Cyan
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

    if ($null -eq $connections -or $connections.Count -eq 0) {
        Write-Host "  Port $Port is clear" -ForegroundColor Green
        return
    }

    $processIds = $connections.OwningProcess | Select-Object -Unique | Where-Object { $_ -ne 0 }
    Write-Host "  Found PIDs on port: $($processIds -join ', ')" -ForegroundColor Yellow

    # Step 2: Kill each process tree
    foreach ($procId in $processIds) {
        Stop-ProcessTree -ProcessId $procId
    }

    # Step 3: Hunt for orphaned Python processes (parent PID doesn't exist)
    Write-Host "  Hunting orphaned Python processes..." -ForegroundColor Cyan
    $pythonProcesses = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' }

    foreach ($proc in $pythonProcesses) {
        # Check if parent process exists
        $parentExists = Get-Process -Id $proc.ParentProcessId -ErrorAction SilentlyContinue
        if ($null -eq $parentExists) {
            # Parent is dead - this is likely an orphan
            # Extra check: is it uvicorn-related?
            if ($proc.CommandLine -match 'uvicorn|fastapi') {
                Write-Host "  Found orphaned uvicorn process: PID $($proc.ProcessId)" -ForegroundColor Yellow
                Stop-ProcessTree -ProcessId $proc.ProcessId
            }
        }
    }

    # Brief pause to let Windows release the port
    Start-Sleep -Milliseconds 500

    # Step 4: Verify port is clear
    $stillOpen = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -ne $stillOpen -and $stillOpen.Count -gt 0) {
        $remainingPids = $stillOpen.OwningProcess | Select-Object -Unique | Where-Object { $_ -ne 0 }
        Write-Host "  WARNING: Port still held by PIDs: $($remainingPids -join ', ')" -ForegroundColor Red
        Write-Host "  Attempting aggressive cleanup..." -ForegroundColor Red

        foreach ($zombiePid in $remainingPids) {
            # Try to find and kill any children of these zombie PIDs
            $orphans = Get-CimInstance Win32_Process | Where-Object {
                $_.ParentProcessId -eq $zombiePid -and $_.Name -match 'python'
            }
            foreach ($orphan in $orphans) {
                Write-Host "    Killing orphan: $($orphan.Name) PID $($orphan.ProcessId)" -ForegroundColor Yellow
                & taskkill /PID $orphan.ProcessId /F 2>&1 | Out-Null
            }
        }

        Start-Sleep -Milliseconds 500

        # Final check
        $finalCheck = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($null -ne $finalCheck -and $finalCheck.Count -gt 0) {
            Write-Host "  CRITICAL: Could not clear port $Port!" -ForegroundColor Red
            Write-Host "  You may need to restart Windows or manually kill processes" -ForegroundColor Red
            Write-Host "  Try: netstat -ano | findstr :$Port" -ForegroundColor Yellow
        } else {
            Write-Host "  Port $Port cleared after aggressive cleanup" -ForegroundColor Green
        }
    } else {
        Write-Host "  Port $Port is now clear" -ForegroundColor Green
    }
}

# Execute the cleanup
Stop-PortProcesses -Port $Port

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
Write-Host ""
Write-Host "NOTE: If you made code changes, verify the server reloaded by checking" -ForegroundColor Cyan
Write-Host "      the new PowerShell window for 'WatchFiles detected changes'" -ForegroundColor Cyan
