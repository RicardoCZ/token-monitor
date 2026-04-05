# Token Monitor backend one-click start (Windows): stop old listener -> check port -> uvicorn -> status
# Mirrors backend/start.sh

$ErrorActionPreference = 'Stop'

$Port = 5188
$BackendDir = $PSScriptRoot
$LogDir = Join-Path $BackendDir 'logs'
$LogFile = Join-Path $LogDir 'backend.log'
$VenvDir = Join-Path $BackendDir '.venv'
$ReqFile = Join-Path $BackendDir 'requirements.txt'

Set-Location -LiteralPath $BackendDir
Write-Host "==> 工作目录: $BackendDir"

function Get-SystemPython {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ FilePath = (Get-Command py).Source; Args = @('-3') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ FilePath = (Get-Command python).Source; Args = @() }
    }
    Write-Host '==> 错误: 未找到 Python（需要 PATH 中有 py 或 python）' -ForegroundColor Red
    exit 1
}

function New-VenvIfMissing {
    if (Test-Path -LiteralPath $VenvDir) {
        Write-Host "==> 虚拟环境已存在: $VenvDir"
        return
    }
    Write-Host "==> 创建虚拟环境: $VenvDir"
    $sysPy = Get-SystemPython
    $venvArgs = $sysPy.Args + @('-m', 'venv', $VenvDir)
    & $sysPy.FilePath $venvArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host '==> 错误: 创建虚拟环境失败' -ForegroundColor Red
        exit 1
    }
}

function Install-DepsIfMissing {
    $pipPath = Join-Path $VenvDir 'Scripts\pip.exe'
    $pythonPath = Join-Path $VenvDir 'Scripts\python.exe'
    
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $checkOut = & $pythonPath -c 'import app' 2>&1
    $checkExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    
    if ($checkExit -eq 0) {
        Write-Host "==> 依赖已安装"
        return
    }
    
    Write-Host '==> 安装依赖: pip install -r requirements.txt'
    & $pipPath 'install' '-r' $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host '==> 错误: pip install 失败' -ForegroundColor Red
        exit 1
    }
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

New-VenvIfMissing
Install-DepsIfMissing

$pythonPath = Join-Path $VenvDir 'Scripts\python.exe'
$pyCmdLine = "`"$pythonPath`" -m uvicorn app:app --host 0.0.0.0 --port $Port"

# Combined stdout/stderr into one log (same as start.sh); cmd avoids nested PowerShell quoting
$runCmd = "cd /d `"$BackendDir`" && set PYTHONUNBUFFERED=1 && $pyCmdLine > `"$LogFile`" 2>&1"
Write-Host "==> 启动: $pyCmdLine（日志: $LogFile）"

$proc = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', $runCmd) -WindowStyle Hidden -PassThru
Write-Host "==> 已后台启动，CMD 包装 PID=$($proc.Id)，日志: $LogFile"

# lifespan 内会先 await init_db() 等，完成后 Uvicorn 才 bind；2s 在 Windows/远端 MySQL 上常误判失败，故轮询等待。
$maxWaitSec = 45
$listenAfter = @()
for ($i = 0; $i -lt $maxWaitSec; $i++) {
    Start-Sleep -Seconds 1
    $listenAfter = Get-ListenerPids -LocalPort $Port
    if ($listenAfter.Count -gt 0) { break }
    if (($i + 1) % 5 -eq 0) {
        Write-Host "==> 仍在等待端口 $Port 监听… ($($i + 1)s / ${maxWaitSec}s，应用启动中或数据库较慢)" -ForegroundColor DarkGray
    }
}

if ($listenAfter.Count -eq 0) {
    $cmdAlive = $false
    try {
        $null = Get-Process -Id $proc.Id -ErrorAction Stop
        $cmdAlive = $true
    } catch {
        $cmdAlive = $false
    }
    Write-Host '==> 警告: 等待超时仍未检测到端口监听。日志尾部:' -ForegroundColor Yellow
    if (Test-Path -LiteralPath $LogFile) {
        Get-Content -LiteralPath $LogFile -Tail 40 -ErrorAction SilentlyContinue
    } else {
        Write-Host '(日志文件尚不存在或路径无效)'
    }
    if (-not $cmdAlive) {
        Write-Host '==> CMD 包装进程已退出，多半是启动崩溃。请根据上方日志排查（常见：MySQL 未启动、.env 库连不上）。' -ForegroundColor Red
    } else {
        Write-Host '==> CMD 仍在运行但未监听端口，请查看日志是否卡在数据库或 lifespan。' -ForegroundColor Red
    }
    exit 1
}

Write-Host "==> 状态: 端口 $Port 正在监听"
Write-Host "==> 完成。查看日志: Get-Content -Tail 50 -Wait -LiteralPath '$LogFile'"
