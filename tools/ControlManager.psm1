# ControlManager PowerShell Module
# Provides command-line control of the lab system

$script:DefaultServer = "localhost"
$script:DefaultPort = 5557
$script:Context = $null
$script:Socket = $null

function Connect-LabManager {
    <#
    .SYNOPSIS
        Connect to the ControlManager server.
    
    .PARAMETER Server
        Server hostname or IP (default: localhost)
    
    .PARAMETER Port
        ZMQ port (default: 5557)
    
    .EXAMPLE
        Connect-LabManager
        Connect-LabManager -Server "192.168.1.100" -Port 5557
    #>
    [CmdletBinding()]
    param(
        [string]$Server = $script:DefaultServer,
        [int]$Port = $script:DefaultPort
    )
    
    try {
        # Load ZeroMQ via Python (since we don't have native ZMQ in PowerShell easily)
        $pythonCode = @"
import zmq
import json

ctx = zmq.Context()
socket = ctx.socket(zmq.REQ)
socket.connect("tcp://$($Server):$($Port)")
socket.setsockopt(zmq.RCVTIMEO, 5000)

# Test connection
socket.send_json({"action": "STATUS"})
response = socket.recv_json()
print(json.dumps(response))

socket.close()
ctx.term()
"@
        
        $response = python -c $pythonCode 2>&1 | Out-String
        $result = $response | ConvertFrom-Json
        
        if ($result.status -eq "success" -or $result.mode) {
            $script:DefaultServer = $Server
            $script:DefaultPort = $Port
            Write-Host "✓ Connected to ControlManager at $($Server):$($Port)" -ForegroundColor Green
            Write-Host "  Mode: $($result.mode)" -ForegroundColor Cyan
            return $result
        } else {
            Write-Error "Failed to connect: $($result.message)"
        }
    } catch {
        Write-Error "Connection failed: $_"
    }
}

function Send-LabCommand {
    <#
    .SYNOPSIS
        Send a command to the ControlManager.
    
    .PARAMETER Action
        Command action (SET, GET, STATUS, OPTIMIZE_START, etc.)
    
    .PARAMETER Parameters
        Command parameters as hashtable
    
    .EXAMPLE
        Send-LabCommand -Action "STATUS"
        Send-LabCommand -Action "SET" -Parameters @{"piezo" = 2.5}
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Action,
        
        [hashtable]$Parameters = @{},
        
        [string]$Server = $script:DefaultServer,
        [int]$Port = $script:DefaultPort
    )
    
    $paramsJson = $Parameters | ConvertTo-Json -Compress
    
    $pythonCode = @"
import zmq
import json

ctx = zmq.Context()
socket = ctx.socket(zmq.REQ)
socket.connect("tcp://$($Server):$($Port)")
socket.setsockopt(zmq.RCVTIMEO, 10000)

cmd = {
    "action": "$($Action)",
    "source": "POWERSHELL",
    "timestamp": __import__('time').time()
}

params = json.loads('$($paramsJson)')
cmd.update(params)

socket.send_json(cmd)
response = socket.recv_json()
print(json.dumps(response))

socket.close()
ctx.term()
"@
    
    try {
        $response = python -c $pythonCode 2>&1 | Out-String
        return $response | ConvertFrom-Json
    } catch {
        Write-Error "Command failed: $_"
        return $null
    }
}

function Get-LabStatus {
    <#
    .SYNOPSIS
        Get current system status.
    #>
    Send-LabCommand -Action "STATUS"
}

function Set-LabParameter {
    <#
    .SYNOPSIS
        Set a hardware parameter.
    
    .PARAMETER Name
        Parameter name (piezo, u_rf_volts, etc.)
    
    .PARAMETER Value
        Parameter value
    
    .EXAMPLE
        Set-LabParameter -Name "piezo" -Value 2.5
        Set-LabParameter -Name "be_oven" -Value 1
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]
        [string]$Name,
        
        [Parameter(Mandatory=$true)]
        [object]$Value
    )
    
    $result = Send-LabCommand -Action "SET" -Parameters @{
        params = @{
            $Name = $Value
        }
    }
    
    if ($result.status -eq "success") {
        Write-Host "✓ Set $Name = $Value" -ForegroundColor Green
    } else {
        Write-Error "Failed to set $Name`: $($result.message)"
    }
    
    return $result
}

function Get-LabParameter {
    <#
    .SYNOPSIS
        Get current parameter values.
    
    .PARAMETER Name
        Specific parameter to get (optional)
    #>
    [CmdletBinding()]
    param([string]$Name = $null)
    
    $params = @{}
    if ($Name) {
        $params["params"] = @($Name)
    }
    
    return Send-LabCommand -Action "GET" -Parameters $params
}

function Start-LabOptimization {
    <#
    .SYNOPSIS
        Start Bayesian optimization.
    
    .PARAMETER TargetBeCount
        Target number of Be+ ions (default: 1)
    
    .PARAMETER TargetHdPresent
        Whether to load HD+ (default: true)
    
    .PARAMETER MaxIterations
        Maximum iterations (default: 50)
    
    .EXAMPLE
        Start-LabOptimization
        Start-LabOptimization -TargetBeCount 2 -MaxIterations 100
    #>
    [CmdletBinding()]
    param(
        [int]$TargetBeCount = 1,
        [bool]$TargetHdPresent = $true,
        [int]$MaxIterations = 50
    )
    
    Write-Host "Starting optimization..." -ForegroundColor Yellow
    Write-Host "  Target Be+ count: $TargetBeCount" -ForegroundColor Cyan
    Write-Host "  Load HD+: $TargetHdPresent" -ForegroundColor Cyan
    Write-Host "  Max iterations: $MaxIterations" -ForegroundColor Cyan
    
    $result = Send-LabCommand -Action "OPTIMIZE_START" -Parameters @{
        target_be_count = $TargetBeCount
        target_hd_present = $TargetHdPresent
        max_iterations = $MaxIterations
    }
    
    if ($result.status -eq "success") {
        Write-Host "✓ Optimization started (Exp ID: $($result.exp_id))" -ForegroundColor Green
    } else {
        Write-Error "Failed to start: $($result.message)"
    }
    
    return $result
}

function Stop-LabOptimization {
    <#
    .SYNOPSIS
        Stop optimization.
    #>
    $result = Send-LabCommand -Action "OPTIMIZE_STOP"
    
    if ($result.status -eq "success") {
        Write-Host "✓ Optimization stopped" -ForegroundColor Green
    } else {
        Write-Error "Failed to stop: $($result.message)"
    }
    
    return $result
}

function Get-LabOptimizationStatus {
    <#
    .SYNOPSIS
        Get optimization status.
    #>
    $result = Send-LabCommand -Action "OPTIMIZE_STATUS"
    
    if ($result.data) {
        Write-Host "Optimization Status:" -ForegroundColor Yellow
        Write-Host "  Phase: $($result.data.phase)" -ForegroundColor Cyan
        Write-Host "  Iteration: $($result.data.iteration)" -ForegroundColor Cyan
        Write-Host "  Best Cost: $($result.data.best_cost)" -ForegroundColor Cyan
        if ($result.data.convergence_delta) {
            Write-Host "  Convergence: $($result.data.convergence_delta)" -ForegroundColor Cyan
        }
    }
    
    return $result
}

function Watch-LabOptimization {
    <#
    .SYNOPSIS
        Watch optimization progress in real-time.
    
    .PARAMETER Interval
        Update interval in seconds (default: 2)
    
    .EXAMPLE
        Watch-LabOptimization
        Watch-LabOptimization -Interval 5
    #>
    [CmdletBinding()]
    param([int]$Interval = 2)
    
    Write-Host "Watching optimization (Ctrl+C to stop)..." -ForegroundColor Yellow
    
    try {
        while ($true) {
            Clear-Host
            $status = Get-LabOptimizationStatus
            
            if ($status.data.phase -eq "complete") {
                Write-Host "`n✓ Optimization complete!" -ForegroundColor Green
                break
            }
            
            Start-Sleep -Seconds $Interval
        }
    } catch {
        Write-Host "`nStopped watching." -ForegroundColor Yellow
    }
}

function Set-LabSafeMode {
    <#
    .SYNOPSIS
        Enter SAFE mode (emergency stop).
    #>
    $result = Send-LabCommand -Action "MODE" -Parameters @{
        mode = "SAFE"
    }
    
    if ($result.status -eq "success") {
        Write-Host "✓ Entered SAFE mode" -ForegroundColor Red
    }
    
    return $result
}

function Set-LabAutoMode {
    <#
    .SYNOPSIS
        Enter AUTO mode (for optimization).
    #>
    $result = Send-LabCommand -Action "MODE" -Parameters @{
        mode = "AUTO"
    }
    
    if ($result.status -eq "success") {
        Write-Host "✓ Entered AUTO mode" -ForegroundColor Green
    }
    
    return $result
}

# Export functions
Export-ModuleMember -Function @(
    'Connect-LabManager',
    'Send-LabCommand',
    'Get-LabStatus',
    'Set-LabParameter',
    'Get-LabParameter',
    'Start-LabOptimization',
    'Stop-LabOptimization',
    'Get-LabOptimizationStatus',
    'Watch-LabOptimization',
    'Set-LabSafeMode',
    'Set-LabAutoMode'
)
