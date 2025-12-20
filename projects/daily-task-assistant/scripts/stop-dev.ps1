# PowerShell script to stop local backend/frontend dev servers.
# Handles orphaned uvicorn child processes that can survive parent termination.

function Stop-PortProcess {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        Write-Host "No process found on port $Port"
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
                Write-Host "Stopping process $procId on port $Port..."
                Stop-Process -Id $procId -Force
            } else {
                # Parent is dead but port still held - zombie situation
                $orphanedParents += $procId
                Write-Host "Parent PID $procId is dead (zombie)" -ForegroundColor DarkYellow
            }
        } catch {
            $orphanedParents += $procId
            Write-Host "Parent PID $procId not found (zombie)" -ForegroundColor DarkYellow
        }
    }

    # Kill orphaned child processes (uvicorn/node children whose parents died)
    if ($orphanedParents.Count -gt 0) {
        Write-Host "Hunting orphaned children of zombie parents..." -ForegroundColor Yellow
        $orphans = Get-CimInstance Win32_Process | Where-Object {
            $_.ParentProcessId -in $orphanedParents -and $_.Name -match 'python|node'
        }
        foreach ($orphan in $orphans) {
            try {
                Write-Host "Killing orphan $($orphan.Name) (PID $($orphan.ProcessId))..." -ForegroundColor Yellow
                Stop-Process -Id $orphan.ProcessId -Force
            } catch {
                Write-Warning ("Failed to kill orphan PID {0}: {1}" -f $orphan.ProcessId, $_)
            }
        }
    }
}

Stop-PortProcess -Port 8000
Stop-PortProcess -Port 5173

Write-Host "Done."

