# Token Monitor backend one-click start (Windows): stop old listener -> check port -> uvicorn -> status
# Mirrors backend/start.sh

$ErrorActionPreference = 'Stop'

$Port = 5188
$BackendDir = $PSScriptRoot
$LogDir = Join-Path $BackendDir 'logs'
$LogFile = Join-Path $LogDir 'backend.log'

Set-Location -LiteralPath $BackendDir
Write-Host "==> 工作目录: $BackendDir"

function Get-PythonLaunchInfo {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{
            FilePath = (Get-Command py).Source
            ArgumentPrefix = @('-3')
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{
            FilePath = (Get-Command python).Source
            ArgumentPrefix = @()
        }
    }
    Write-Host '==> 错误: 未找到 Python（需要 PATH 中有 py 或 python）' -ForegroundColor Red
    exit 1
}

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

function Stop-ListenersOnPort([int] $LocalPort) {
    $pids = Get-ListenerPids -LocalPort $LocalPort
    if ($pids.Count -eq 0) {
        Write-Host "==> 未发现监听端口 $LocalPort 的旧进程"
        return
    }
    Write-Host "==> 停止占用端口 $LocalPort 的进程: $($pids -join ' ')"
    foreach ($procId in $pids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
    $still = Get-ListenerPids -LocalPort $LocalPort
    if ($still.Count -gt 0) {
        Write-Host "==> 强制结束: $($still -join ' ')"
        foreach ($procId in $still) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
    }
}

Stop-ListenersOnPort -LocalPort $Port

$remaining = Get-ListenerPids -LocalPort $Port
if ($remaining.Count -gt 0) {
    Write-Host "==> 错误: 端口 $Port 仍被占用，请手动处理后重试。" -ForegroundColor Red
    exit 1
}
Write-Host "==> 端口 $Port 可用"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$py = Get-PythonLaunchInfo

# Ensure same interpreter as uvicorn can import the app (avoids fresh Windows env without pip deps)
$reqFile = Join-Path $BackendDir 'requirements.txt'
$depCheckArgs = if ($py.ArgumentPrefix.Count -gt 0) {
    @('-3', '-c', 'import app')
} else {
    @('-c', 'import app')
}
& $py.FilePath $depCheckArgs 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host '==> 缺少依赖，正在 pip install -r requirements.txt ...'
    $pipArgs = if ($py.ArgumentPrefix.Count -gt 0) {
        @('-3', '-m', 'pip', 'install', '-r', $reqFile)
    } else {
        @('-m', 'pip', 'install', '-r', $reqFile)
    }
    & $py.FilePath $pipArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host '==> 错误: pip install 失败，请在 backend 目录手动执行 py -3 -m pip install -r requirements.txt' -ForegroundColor Red
        exit 1
    }
    & $py.FilePath $depCheckArgs 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '==> 错误: 依赖已安装但仍无法 import app，请查看日志或手动运行 py -3 -c "import app"' -ForegroundColor Red
        exit 1
    }
}

$pyCmdLine = if ($py.ArgumentPrefix.Count -gt 0) {
    "py -3 -m uvicorn app:app --host 0.0.0.0 --port $Port"
} else {
    "python -m uvicorn app:app --host 0.0.0.0 --port $Port"
}

# Combined stdout/stderr into one log (same as start.sh); cmd avoids nested PowerShell quoting
$runCmd = "cd /d `"$BackendDir`" && set PYTHONUNBUFFERED=1 && $pyCmdLine > `"$LogFile`" 2>&1"
Write-Host "==> 启动: $pyCmdLine（日志: $LogFile）"

$proc = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $runCmd) -WindowStyle Hidden -PassThru
Write-Host "==> 已后台启动，CMD 包装 PID=$($proc.Id)，日志: $LogFile"

Start-Sleep -Seconds 2

$listenAfter = Get-ListenerPids -LocalPort $Port
if ($listenAfter.Count -eq 0) {
    Write-Host '==> 警告: 暂未检测到端口监听，可能启动失败。日志尾部:' -ForegroundColor Yellow
    if (Test-Path -LiteralPath $LogFile) {
        Get-Content -LiteralPath $LogFile -Tail 30 -ErrorAction SilentlyContinue
    }
    exit 1
}

Write-Host "==> 状态: 端口 $Port 正在监听"
Write-Host "==> 完成。查看日志: Get-Content -Tail 50 -Wait -LiteralPath '$LogFile'"
