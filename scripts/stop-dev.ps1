# PowerShell script to stop local backend/frontend dev servers.

function Stop-PortProcess {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($null -eq $connections) {
        Write-Host "No process found on port $Port"
        return
    }
    $pids = $connections.OwningProcess | Select-Object -Unique
    foreach ($procId in $pids) {
        if ($procId -le 0) {
            continue
        }
        try {
            Write-Host "Stopping process $procId on port $Port..."
            Stop-Process -Id $procId -Force
        } catch {
            Write-Warning ("Failed to stop PID {0}: {1}" -f $procId, $_)
        }
    }
}

Stop-PortProcess -Port 8000
Stop-PortProcess -Port 5173

Write-Host "Done."

