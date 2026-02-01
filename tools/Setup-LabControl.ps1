# Setup script for LabControl PowerShell module

$ModulePath = "$PSScriptRoot\ControlManager.psm1"

function Test-PythonZMQ {
    try {
        $result = python -c "import zmq; print('OK')" 2>&1
        return $result -eq "OK"
    } catch {
        return $false
    }
}

function Install-Requirements {
    Write-Host "Installing Python requirements..." -ForegroundColor Yellow
    
    $Requirements = @"
pyzmq>=25.0
numpy>=1.24.0
pyyaml>=6.0
"@
    
    $reqFile = [System.IO.Path]::GetTempFileName()
    $Requirements | Out-File -FilePath $reqFile -Encoding ASCII
    
    python -m pip install -r $reqFile
    
    Remove-Item $reqFile
}

# Check Python
Write-Host "Checking Python..." -ForegroundColor Cyan
try {
    $pyVersion = python --version 2>&1
    Write-Host "  ✓ $pyVersion" -ForegroundColor Green
} catch {
    Write-Error "Python not found. Please install Python 3.10+"
    exit 1
}

# Check ZMQ
Write-Host "Checking ZeroMQ..." -ForegroundColor Cyan
if (Test-PythonZMQ) {
    Write-Host "  ✓ ZeroMQ installed" -ForegroundColor Green
} else {
    Write-Host "  ✗ ZeroMQ not found" -ForegroundColor Red
    $install = Read-Host "Install requirements? (y/n)"
    if ($install -eq 'y') {
        Install-Requirements
    }
}

# Install module
Write-Host "`nInstalling PowerShell module..." -ForegroundColor Cyan

$ModulesDir = "$HOME\Documents\PowerShell\Modules\LabControl"
if (-not (Test-Path $ModulesDir)) {
    New-Item -ItemType Directory -Path $ModulesDir -Force | Out-Null
}

Copy-Item $ModulePath "$ModulesDir\LabControl.psm1" -Force

# Create module manifest
$ManifestPath = "$ModulesDir\LabControl.psd1"
$Manifest = @"
@{
    RootModule = 'LabControl.psm1'
    ModuleVersion = '1.0.0'
    GUID = '12345678-1234-1234-1234-123456789012'
    Author = 'Lab Control Team'
    Description = 'PowerShell interface for LabControlManager'
    FunctionsToExport = @(
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
}
"@

$Manifest | Out-File -FilePath $ManifestPath -Force

Write-Host "  ✓ Module installed to $ModulesDir" -ForegroundColor Green

# Create launcher script
$LauncherPath = "$PSScriptRoot\Start-ControlManager.ps1"
$Launcher = @"
# Start ControlManager
`$ProjectRoot = "$PSScriptRoot\.."
Set-Location `$ProjectRoot

Write-Host "Starting ControlManager..." -ForegroundColor Green
Write-Host "  Project: `$ProjectRoot" -ForegroundColor Gray

python -m server.control_manager
"@

$Launcher | Out-File -FilePath $LauncherPath -Force
Write-Host "  ✓ Launcher created: $LauncherPath" -ForegroundColor Green

# Instructions
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "`nUsage:" -ForegroundColor Cyan
Write-Host "  1. Start ControlManager:" -ForegroundColor White
Write-Host "     .\tools\Start-ControlManager.ps1" -ForegroundColor Gray
Write-Host "`n  2. In another PowerShell window:" -ForegroundColor White
Write-Host "     Import-Module LabControl" -ForegroundColor Gray
Write-Host "     Connect-LabManager" -ForegroundColor Gray
Write-Host "     Get-LabStatus" -ForegroundColor Gray
Write-Host "`n  3. Control examples:" -ForegroundColor White
Write-Host "     Set-LabParameter -Name 'piezo' -Value 2.5" -ForegroundColor Gray
Write-Host "     Start-LabOptimization -TargetBeCount 1" -ForegroundColor Gray
Write-Host "     Watch-LabOptimization" -ForegroundColor Gray
Write-Host "`n  4. Emergency stop:" -ForegroundColor White
Write-Host "     Set-LabSafeMode" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Yellow
