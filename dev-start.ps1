# aBaiAutoplus 开发模式启动脚本
# Author: wangqiupei
# Description: 一键启动前端+后端开发服务器

param(
    [switch]$SkipCheck,  # 跳过依赖检查
    [switch]$NoBrowser   # 不自动打开浏览器
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ===== 配置 =====
$BackendPort = 8000
$FrontendPort = 5173
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
$PipExe = Join-Path $Root ".venv\Scripts\pip.exe"
$ActivateScript = Join-Path $Root ".venv\Scripts\Activate.ps1"

# ===== 颜色输出函数 =====
function Write-Info { param([string]$msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Success { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warning { param([string]$msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Error-Custom { param([string]$msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

# ===== 端口检查函数 =====
function Test-TcpPort {
    param([string]$HostName, [int]$Port)
    try {
        $addresses = [System.Net.Dns]::GetHostAddresses($HostName)
    } catch {
        return $false
    }

    foreach ($address in $addresses) {
        $client = New-Object System.Net.Sockets.TcpClient($address.AddressFamily)
        try {
            $async = $client.BeginConnect($address, $Port, $null, $null)
            if (-not $async.AsyncWaitHandle.WaitOne(500)) { continue }
            $client.EndConnect($async)
            return $true
        } catch {
            continue
        } finally {
            $client.Close()
        }
    }

    return $false
}

# ===== 等待端口就绪 =====
function Wait-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

# ===== 清理函数 =====
$script:BackendProcess = $null
$script:FrontendProcess = $null

function Stop-ProcessTree {
    param([int]$ProcessId)

    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-ProcessTree -ProcessId $child.ProcessId
        }

        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {
        # 进程可能已退出，忽略清理期竞态
    }
}

function Stop-Services {
    Write-Host ""
    Write-Info "正在停止服务..."

    if ($script:FrontendProcess) {
        Write-Info "停止前端服务 (PID: $($script:FrontendProcess.Id))"
        Stop-ProcessTree -ProcessId $script:FrontendProcess.Id
    }

    if ($script:BackendProcess) {
        Write-Info "停止后端服务 (PID: $($script:BackendProcess.Id))"
        Stop-ProcessTree -ProcessId $script:BackendProcess.Id
    }

    Write-Success "所有服务已停止"
}

# 注册 Ctrl+C 处理器
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-Services } | Out-Null

# ===== 主流程 =====
Write-Host "======================================"
Write-Host "  aBaiAutoplus 开发模式启动器"
Write-Host "======================================"
Write-Host ""

# 1. 检查端口占用
Write-Info "检查端口占用..."
if (Test-TcpPort -HostName "127.0.0.1" -Port $BackendPort) {
    Write-Error-Custom "后端端口 $BackendPort 已被占用，请先停止占用该端口的程序"
    exit 1
}
if (Test-TcpPort -HostName "127.0.0.1" -Port $FrontendPort) {
    Write-Error-Custom "前端端口 $FrontendPort 已被占用，请先停止占用该端口的程序"
    exit 1
}
Write-Success "端口检查通过"

if (-not $SkipCheck) {
    # 2. 检查/创建虚拟环境
    Write-Info "检查 Python 虚拟环境..."
    if (-not (Test-Path $PythonExe)) {
        Write-Warning "虚拟环境不存在，正在创建..."
        & python -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) {
            Write-Error-Custom "创建虚拟环境失败"
            exit 1
        }
        Write-Success "虚拟环境创建成功"
    } else {
        Write-Success "虚拟环境已存在"
    }

    # 3. 检查 Python 依赖
    Write-Info "检查 Python 依赖..."
    $requirementsFile = Join-Path $Root "requirements.txt"
    & $PipExe list --format=freeze --disable-pip-version-check 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Python 依赖已安装"
    } else {
        Write-Warning "正在安装 Python 依赖..."
        & $PipExe install -r $requirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-Error-Custom "安装 Python 依赖失败"
            exit 1
        }
        Write-Success "Python 依赖安装成功"
    }

    # 4. 检查 Playwright
    Write-Info "检查 Playwright 浏览器驱动..."
    $playwrightCheck = & $PythonExe -c "import playwright; print('ok')" 2>$null
    if ($playwrightCheck -like "*ok*") {
        Write-Success "Playwright 已安装"
    } else {
        Write-Warning "正在安装 Playwright 浏览器驱动..."
        & $PythonExe -m playwright install chromium
        Write-Success "Playwright 安装成功"
    }

    # 5. 检查前端依赖
    Write-Info "检查前端依赖..."
    $nodeModules = Join-Path $Root "frontend\node_modules"
    if (-not (Test-Path $nodeModules)) {
        Write-Warning "正在安装前端依赖..."
        Push-Location (Join-Path $Root "frontend")
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Pop-Location
            Write-Error-Custom "安装前端依赖失败"
            exit 1
        }
        Pop-Location
        Write-Success "前端依赖安装成功"
    } else {
        Write-Success "前端依赖已安装"
    }
}

Write-Host ""
Write-Info "所有依赖检查完成，准备启动服务..."
Write-Host ""

# 6. 启动后端服务
Write-Info "启动后端服务 (http://localhost:$BackendPort)"
$backendLogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $backendLogDir | Out-Null
$backendLogOut = Join-Path $backendLogDir "backend.out.log"
$backendLogErr = Join-Path $backendLogDir "backend.err.log"

try {
    $script:BackendProcess = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload") `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $backendLogOut `
        -RedirectStandardError $backendLogErr `
        -WindowStyle Hidden `
        -PassThru

    # 等待后端就绪
    Write-Info "等待后端服务启动..."
    Start-Sleep -Seconds 3  # 给进程一些启动时间
    if (-not (Wait-TcpPort -HostName "127.0.0.1" -Port $BackendPort -TimeoutSeconds 30)) {
        # 尝试检查 0.0.0.0 绑定
        if (-not (Get-NetTCPConnection -LocalPort $BackendPort -ErrorAction SilentlyContinue)) {
            Write-Error-Custom "后端服务启动超时，请查看日志:"
            Write-Host "  stdout: $backendLogOut"
            Write-Host "  stderr: $backendLogErr"
            if (Test-Path $backendLogErr) {
                Write-Host ""
                Write-Host "错误日志内容:"
                Get-Content $backendLogErr -Tail 20 | ForEach-Object { Write-Host "  $_" }
            }
            Stop-Services
            exit 1
        }
    }
    Write-Success "后端服务已启动 (PID: $($script:BackendProcess.Id))"

    # 7. 启动前端服务
    Write-Info "启动前端服务 (http://localhost:$FrontendPort)"
    $frontendLogDir = Join-Path $Root "logs"
    $frontendLogOut = Join-Path $frontendLogDir "frontend.out.log"
    $frontendLogErr = Join-Path $frontendLogDir "frontend.err.log"

    # 使用 cmd.exe 启动 npm（避免 PowerShell 脚本执行策略问题）
    $script:FrontendProcess = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "npm", "run", "dev") `
        -WorkingDirectory (Join-Path $Root "frontend") `
        -RedirectStandardOutput $frontendLogOut `
        -RedirectStandardError $frontendLogErr `
        -WindowStyle Hidden `
        -PassThru

    # 等待前端就绪
    Write-Info "等待前端服务启动..."
    Start-Sleep -Seconds 3  # 给进程一些启动时间
    if (-not (Wait-TcpPort -HostName "localhost" -Port $FrontendPort -TimeoutSeconds 30)) {
        # 尝试检查端口绑定
        if (-not (Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue)) {
            Write-Error-Custom "前端服务启动超时，请查看日志:"
            Write-Host "  stdout: $frontendLogOut"
            Write-Host "  stderr: $frontendLogErr"
            if (Test-Path $frontendLogErr) {
                Write-Host ""
                Write-Host "错误日志内容:"
                Get-Content $frontendLogErr -Tail 20 | ForEach-Object { Write-Host "  $_" }
            }
            Stop-Services
            exit 1
        }
    }
    Write-Success "前端服务已启动 (PID: $($script:FrontendProcess.Id))"

    Write-Host ""
    Write-Host "======================================" -ForegroundColor Green
    Write-Host "  服务启动成功！" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  前端地址: " -NoNewline
    Write-Host "http://localhost:$FrontendPort" -ForegroundColor Cyan
    Write-Host "  后端地址: " -NoNewline
    Write-Host "http://localhost:$BackendPort" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  后端日志: $backendLogOut | $backendLogErr"
    Write-Host "  前端日志: $frontendLogOut | $frontendLogErr"
    Write-Host ""
    Write-Host "  按 Ctrl+C 停止所有服务" -ForegroundColor Yellow
    Write-Host ""

    # 8. 打开浏览器
    if (-not $NoBrowser) {
        Start-Sleep -Seconds 2
        Start-Process "http://localhost:$FrontendPort"
    }

    # 9. 保持脚本运行，等待用户中断
    Write-Info "服务正在运行中..."
    while ($true) {
        Start-Sleep -Seconds 5

        # 检查进程是否还在运行
        if ($script:BackendProcess.HasExited) {
            Write-Error-Custom "后端服务意外退出，退出码: $($script:BackendProcess.ExitCode)"
            break
        }
        if ($script:FrontendProcess.HasExited) {
            Write-Error-Custom "前端服务意外退出，退出码: $($script:FrontendProcess.ExitCode)"
            break
        }
    }

} catch {
    Write-Error-Custom "启动失败: $_"
    Stop-Services
    exit 1
} finally {
    Stop-Services
}
