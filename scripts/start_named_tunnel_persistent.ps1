<#
.SYNOPSIS
    Persistent launcher and watchdog for the Cloudflare Named Tunnel (handover-ai-gateway).

.DESCRIPTION
    Waits for the Local AI Gateway (127.0.0.1:8002) to become healthy, loads the validated
    configuration from C:\Users\ASUS\.cloudflared\config.yml, connects the named tunnel to
    Cloudflare edge data centers, and automatically reconnects across network disconnections.

.NOTES
    Milestone: M4.3.2.1
    Tunnel Name: handover-ai-gateway
    Target Hostname: ai-gateway.the-sapiens.xyz
#>

[CmdletBinding()]
param(
    [string]$CloudflaredExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    [string]$ConfigFile = "C:\Users\ASUS\.cloudflared\config.yml",
    [string]$TunnelName = "handover-ai-gateway",
    [int]$MaxRestarts = 20,
    [int]$RestartDelaySec = 5
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $PSScriptRoot "..\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$LogFile = Join-Path $LogDir "named_tunnel_service.log"

function Write-TunnelLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $entry = "[$timestamp] [$Level] $Message"
    Write-Host $entry
    Add-Content -Path $LogFile -Value $entry
}

Write-TunnelLog "Initializing Cloudflare Named Tunnel Watchdog ($TunnelName)..."

# 1. Verify cloudflared executable and config
if (-not (Test-Path $CloudflaredExe)) {
    Write-TunnelLog "FATAL: cloudflared.exe not found at $CloudflaredExe" "ERROR"
    exit 1
}
if (-not (Test-Path $ConfigFile)) {
    Write-TunnelLog "FATAL: Tunnel configuration not found at $ConfigFile" "ERROR"
    exit 1
}

# 2. Dependency Ordering: Wait for Gateway on 127.0.0.1:8002
Write-TunnelLog "Checking Local AI Gateway (127.0.0.1:8002)..."
$gatewayReady = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -TimeoutSec 2 -ErrorAction Stop
        if ($res.status -eq "ok") {
            $gatewayReady = $true
            Write-TunnelLog "Local AI Gateway is ready on 127.0.0.1:8002."
            break
        }
    } catch {
        Write-TunnelLog "Waiting for Local AI Gateway on 127.0.0.1:8002 (Attempt $attempt/30)..." "WARN"
        Start-Sleep -Seconds 2
    }
}

if (-not $gatewayReady) {
    Write-TunnelLog "WARNING: Gateway not responding. Proceeding to launch tunnel (will retry origin upon ingress)..." "WARN"
}

# 3. Tunnel Run Loop
$restartCount = 0
while ($restartCount -lt $MaxRestarts) {
    Write-TunnelLog "Connecting Cloudflare Named Tunnel: $TunnelName (Attempt $($restartCount + 1))..."

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $CloudflaredExe
    $psi.Arguments = "tunnel --config `"$ConfigFile`" run $TunnelName"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false

    try {
        $process = [System.Diagnostics.Process]::Start($psi)
        Write-TunnelLog "Cloudflared tunnel process started with PID $($process.Id)."

        # Wait for tunnel process exit
        $process.WaitForExit()
        $exitCode = $process.ExitCode
        Write-TunnelLog "Cloudflared process PID $($process.Id) exited with code $exitCode." "WARN"
    } catch {
        Write-TunnelLog "Error running cloudflared: $($_.Exception.Message)" "ERROR"
    }

    $restartCount++
    if ($restartCount -lt $MaxRestarts) {
        Write-TunnelLog "Reconnecting in $RestartDelaySec seconds..."
        Start-Sleep -Seconds $RestartDelaySec
    }
}

Write-TunnelLog "Maximum tunnel restart limit reached ($MaxRestarts). Watchdog terminating." "ERROR"
