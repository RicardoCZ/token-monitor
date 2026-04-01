# Token Monitor backend stop script (Windows)
# 关闭占用 5188 端口的进程

$ErrorActionPreference = 'Stop'
$Port = 5188

function Get-ListenerPids([int] $LocalPort) {
    $pids = [System.Collections.Generic.HashSet[int]]::new()
    try {
        $conns = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -gt 0) {
                [void]$pids.Add([int]$c.OwningProcess)
            }
        }
    } catch {
        # Older systems: ignore and try netstat
    }
    if ($pids.Count -eq 0) {
        $pattern = ':' + $LocalPort + '\s+.*LISTENING\s+(\d+)\s*$'
        netstat -ano | ForEach-Object {
            if ($_ -match $pattern) {
                [void]$pids.Add([int]$Matches[1])
            }
        }
    }
    return @($pids)
}

Write-Host "==> 正在关闭 Token Monitor 后端服务（端口 $Port）..."

$pids = Get-ListenerPids -LocalPort $Port

if ($pids.Count -eq 0) {
    Write-Host "==> 未发现占用端口 $Port 的进程"
    exit 0
}

Write-Host "==> 找到占用端口 $Port 的进程: $($pids -join ', ')"
foreach ($procId in $pids) {
    Write-Host "==> 正在停止 PID: $procId"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

$still = Get-ListenerPids -LocalPort $Port
if ($still.Count -gt 0) {
    Write-Host "==> 仍有进程占用，强制结束..."
    foreach ($procId in $still) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}

$remaining = Get-ListenerPids -LocalPort $Port
if ($remaining.Count -eq 0) {
    Write-Host "==> Token Monitor 后端服务已关闭"
} else {
    Write-Host "==> 警告: 仍有进程占用端口: $($remaining -join ', ')" -ForegroundColor Yellow
}
