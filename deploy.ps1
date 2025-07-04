# M5Stack Deployment Script
# This script compiles Python to .mpy format and deploys to M5Stack device

param(
    [string]$ComPort = "COM19",
    [string]$MainFile = "main.py"
)

Write-Host "M5Stack Deployment Script (with .mpy compilation)" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

# Check if main.py exists
if (-not (Test-Path $MainFile)) {
    Write-Host "Error: $MainFile not found in current directory!" -ForegroundColor Red
    exit 1
}

Write-Host "Using COM port: $ComPort" -ForegroundColor Yellow
Write-Host "Source file: $MainFile" -ForegroundColor Yellow
Write-Host ""

# Get the base filename without extension
$BaseName = [System.IO.Path]::GetFileNameWithoutExtension($MainFile)
$MpyFile = "$BaseName.mpy"

# Step 1: Compile Python to .mpy
Write-Host "Step 1: Compiling $MainFile to $MpyFile..." -ForegroundColor Cyan
try {
    # Check if mpy-cross is available
    $mpyCrossPath = Get-Command mpy-cross -ErrorAction SilentlyContinue
    if (-not $mpyCrossPath) {
        Write-Host "Warning: mpy-cross not found in PATH. Trying alternative methods..." -ForegroundColor Yellow
        
        # Try common installation paths
        $possiblePaths = @(
            "C:\Python*\Scripts\mpy-cross.exe",
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python*\Scripts\mpy-cross.exe",
            "mpy-cross.exe"
        )
        
        $mpyCrossFound = $false
        foreach ($path in $possiblePaths) {
            $resolved = Get-ChildItem $path -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($resolved) {
                $mpyCrossPath = $resolved.FullName
                $mpyCrossFound = $true
                break
            }
        }
        
        if (-not $mpyCrossFound) {
            Write-Host "Error: mpy-cross compiler not found!" -ForegroundColor Red
            Write-Host "Please install it with: pip install mpy-cross" -ForegroundColor Yellow
            Write-Host "Falling back to deploying .py file directly..." -ForegroundColor Yellow
            $MpyFile = $MainFile
        } else {
            Write-Host "Found mpy-cross at: $mpyCrossPath" -ForegroundColor Green
        }
    }
    
    if ($MpyFile -ne $MainFile) {
        & $mpyCrossPath $MainFile
        if ($LASTEXITCODE -eq 0 -and (Test-Path $MpyFile)) {
            Write-Host "✓ Compilation successful! Created $MpyFile" -ForegroundColor Green
        } else {
            Write-Host "✗ Compilation failed! Falling back to .py file" -ForegroundColor Yellow
            $MpyFile = $MainFile
        }
    }
} catch {
    Write-Host "✗ Compilation error: $_" -ForegroundColor Yellow
    Write-Host "Falling back to .py file deployment..." -ForegroundColor Yellow
    $MpyFile = $MainFile
}

Write-Host ""

# Step 2: Copy the file to the device
Write-Host "Step 2: Copying $MpyFile to M5Stack..." -ForegroundColor Cyan
try {
    & mpremote connect $ComPort fs cp $MpyFile :
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ File copied successfully!" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to copy file!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error copying file: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Run the file on the device
Write-Host "Step 3: Running the application on M5Stack..." -ForegroundColor Cyan
try {
    # Determine which file to run based on what was deployed
    $RunFile = if ($MpyFile -eq $MainFile) { $MainFile } else { $BaseName }
    
    & mpremote connect $ComPort run $RunFile
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Application started successfully!" -ForegroundColor Green
    } else {
        Write-Host "✗ Application failed to start!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error running application: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Deployment completed!" -ForegroundColor Green

# Cleanup: Remove the .mpy file if it was created
if ($MpyFile -ne $MainFile -and (Test-Path $MpyFile)) {
    Write-Host "Cleaning up temporary $MpyFile file..." -ForegroundColor Gray
    Remove-Item $MpyFile -Force
}
