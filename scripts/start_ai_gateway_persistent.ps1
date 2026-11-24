<#
.SYNOPSIS
    Persistent, monitored launcher for The Handover Local AI Gateway.

.DESCRIPTION
    Ensures dependency ordering (Docker containers, Ollama), launches the Uvicorn
    gateway process on 127.0.0.1:8002, monitors its liveness, and automatically restarts
    the service upon unexpected process termination.
    Credentials and Bearer tokens are loaded strictly via environment variables (.env)
    and are never logged or exposed.

.NOTES
    Milestone: M4.3.2.1
    Target Port: 127.0.0.1:8002
#>

[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [int]$MaxRestarts = 10,
    [int]$RestartDelaySec = 5
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "ai_gateway_service.log"

function Write-ServiceLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $entry = "[$timestamp] [$Level] $Message"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry
}

Write-ServiceLog "Initializing Local AI Gateway Persistent Launcher..."

# 1. Dependency Pre-Flight Check: Ollama
Write-ServiceLog "Checking Ollama (127.0.0.1:11434)..."
try {
    $ollamaCheck = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -ErrorAction Stop
    Write-ServiceLog "Ollama is healthy. Available models: $(($ollamaCheck.models | ForEach-Object { $_.name }) -join ', ')"
} catch {
    Write-ServiceLog "WARNING: Ollama not responding on 127.0.0.1:11434. Please ensure Ollama is running." "WARN"
}

# 2. Dependency Pre-Flight Check: ChromaDB
Write-ServiceLog "Checking ChromaDB (127.0.0.1:8001)..."
try {
    $chromaCheck = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v2/heartbeat" -TimeoutSec 5 -ErrorAction Stop
    Write-ServiceLog "ChromaDB heartbeat OK."
} catch {
    Write-ServiceLog "WARNING: ChromaDB not responding on 127.0.0.1:8001. Ensure Docker container ipkrh-chromadb is running." "WARN"
}

# 3. Locate Python executable in backend venv
$PythonExe = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source
}
Write-ServiceLog "Using Python executable: $PythonExe"

# 4. Supervisor Loop
$restartCount = 0
while ($restartCount -lt $MaxRestarts) {
    Write-ServiceLog "Starting Local Inference Gateway on 127.0.0.1:8002 (Attempt: $($restartCount + 1))..."
    
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $PythonExe
    $psi.Arguments = "-m uvicorn infrastructure.gateway.main:create_gateway_app --factory --host 127.0.0.1 --port 8002"
    $psi.WorkingDirectory = $ProjectRoot
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false

    try {
        $process = [System.Diagnostics.Process]::Start($psi)
        Write-ServiceLog "Gateway process started with PID $($process.Id)."

        # Wait for health probe to pass
        Start-Sleep -Seconds 3
        $ready = $false
        for ($i = 0; $i -lt 10; $i++) {
            try {
                $health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -TimeoutSec 2 -ErrorAction Stop
                if ($health.status -eq "ok") {
                    $ready = $true
                    Write-ServiceLog "Gateway health probe verified: HTTP 200 OK."
                    break
                }
            } catch {
                Start-Sleep -Seconds 1
            }
        }

        if (-not $ready) {
            Write-ServiceLog "Gateway health check did not respond within 10 seconds." "WARN"
        }

        # Monitor process until exit
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        Write-ServiceLog "Gateway process PID $($process.Id) exited with code $exitCode." "WARN"
    } catch {
        Write-ServiceLog "Error launching gateway process: $($_.Exception.Message)" "ERROR"
    }

    $restartCount++
    if ($restartCount -lt $MaxRestarts) {
        Write-ServiceLog "Waiting $RestartDelaySec seconds before restarting..."
        Start-Sleep -Seconds $RestartDelaySec
    }
}

Write-ServiceLog "Maximum restart limit reached ($MaxRestarts). Service supervisor terminating." "ERROR"
