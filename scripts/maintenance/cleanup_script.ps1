# MLS Project Cleanup Script
# Removes temporary files, __pycache__, and old logs

param(
    [switch]$All = $false,
    [switch]$DryRun = $false,
    [int]$KeepLogs = 30
)

$script:DeletedCount = 0
$script:DeletedSize = 0

function Remove-ItemsSafely {
    param($Path, $Pattern, $Description)
    
    $items = Get-ChildItem -Path $Path -Recurse -Filter $Pattern -ErrorAction SilentlyContinue
    $count = 0
    $size = 0
    
    foreach ($item in $items) {
        $size += $item.Length
        $count++
        
        if (-not $DryRun) {
            Remove-Item $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        Write-Host "  [$Description] $($item.FullName)" -ForegroundColor Yellow
    }
    
    $script:DeletedCount += $count
    $script:DeletedSize += $size
    return $count, $size
}

Write-Host "`n=== MLS Project Cleanup ===`n" -ForegroundColor Cyan
Write-Host "Mode: $(if($DryRun){'DRY RUN (no changes)'}else{'CLEANUP'})"
Write-Host "`n"

# 1. Python Cache
Write-Host "1. Cleaning Python __pycache__..." -ForegroundColor Green
$pycacheCount, $pycacheSize = Remove-ItemsSafely -Path "D:\MLS" -Pattern "__pycache__" -Description "CACHE"
Write-Host "   Found $pycacheCount folders ($(($pycacheSize/1KB).ToString('F2')) KB)`n"

# 2. .pyc files
Write-Host "2. Cleaning .pyc files..." -ForegroundColor Green
$pycCount, $pycSize = Remove-ItemsSafely -Path "D:\MLS" -Pattern "*.pyc" -Description "PYC"
Write-Host "   Found $pycCount files ($(($pycSize/1KB).ToString('F2')) KB)`n"

# 3. Old logs (if -All specified)
if ($All) {
    Write-Host "3. Cleaning old logs (>$KeepLogs days)..." -ForegroundColor Green
    $logPath = "D:\MLS\logs\debug"
    if (Test-Path $logPath) {
        $oldLogs = Get-ChildItem -Path $logPath -Filter "*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepLogs) }
        $logCount = 0
        $logSize = 0
        foreach ($log in $oldLogs) {
            $logSize += $log.Length
            $logCount++
            if (-not $DryRun) {
                Remove-Item $log.FullName -Force
            }
            Write-Host "   [LOG] $($log.Name)" -ForegroundColor Yellow
        }
        $script:DeletedCount += $logCount
        $script:DeletedSize += $logSize
        Write-Host "   Found $logCount log files ($(($logSize/1KB).ToString('F2')) KB)`n"
    }
}

# Summary
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total items: $script:DeletedCount"
Write-Host "Total size: $(($script:DeletedSize/1KB).ToString('F2')) KB ($(($script:DeletedSize/1MB).ToString('F2')) MB)"

if ($DryRun) {
    Write-Host "`nDRY RUN - No files were actually deleted." -ForegroundColor Magenta
    Write-Host "Run without -DryRun to perform cleanup."
}

Write-Host "`nDone!" -ForegroundColor Green
