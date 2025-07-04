# Weather Icon Deployment Script
# Deploys only the weather icons used in weather_icon_mapping
# Supports resuming from failed deployments

param(
    [string]$ComPort = "COM19",
    [string]$BaseDir = ".",
    [string]$RemoteDir = "res",
    [switch]$ForceAll
)

$StatusFile = "deploy_status.json"

Write-Host "Weather Icon Deployment Script" -ForegroundColor Green
Write-Host "===============================" -ForegroundColor Green
Write-Host "COM Port: $ComPort" -ForegroundColor Yellow
Write-Host "Local Base Directory: $BaseDir" -ForegroundColor Yellow
Write-Host "Remote Directory: /$RemoteDir" -ForegroundColor Yellow

# List of weather icons used in the weather_icon_mapping
$AllWeatherIcons = @(
    # Clear sky
    'clear.png',
    'nt_clear.png',
    
    # Few clouds  
    'mostlysunny.png',
    'nt_mostlycloudy.png',
    
    # Scattered clouds
    'partlycloudy.png',
    'nt_partlycloudy.png',
    
    # Broken clouds
    'cloudy.png',
    'nt_cloudy.png',
    
    # Shower rain
    'sleet.png',
    'nt_sleet.png',
    
    # Rain
    'rain.png',
    'nt_rain.png',
    
    # Thunderstorm
    'tstorms.png',
    'nt_tstorms.png',
    
    # Snow
    'snow.png',
    'nt_snow.png',
    
    # Mist
    'fog.png',
    'nt_fog.png',
    
    # Fallback
    'unknown.png'
)

# Load previous deployment status
$DeploymentStatus = @{}
$WeatherIcons = @()

if ((Test-Path $StatusFile) -and -not $ForceAll) {
    try {
        $StatusData = Get-Content $StatusFile | ConvertFrom-Json
        $DeploymentStatus = @{}
        $StatusData.PSObject.Properties | ForEach-Object { $DeploymentStatus[$_.Name] = $_.Value }
        
        # Only deploy icons that failed or haven't been attempted
        $WeatherIcons = $AllWeatherIcons | Where-Object { 
            -not $DeploymentStatus.ContainsKey($_) -or $DeploymentStatus[$_] -ne "Success" 
        }
        
        if ($WeatherIcons.Count -eq 0) {
            Write-Host "All icons have been successfully deployed!" -ForegroundColor Green
            Write-Host "Use -ForceAll to redeploy all icons." -ForegroundColor Yellow
            exit 0
        }
        
        Write-Host "Resuming deployment - found $($WeatherIcons.Count) icons to deploy/retry..." -ForegroundColor Yellow
    } catch {
        Write-Host "Warning: Could not read status file, deploying all icons..." -ForegroundColor Yellow
        $WeatherIcons = $AllWeatherIcons
    }
} else {
    if ($ForceAll) {
        Write-Host "Force mode - deploying all icons..." -ForegroundColor Yellow
    } else {
        Write-Host "First run - deploying all icons..." -ForegroundColor Yellow
    }
    $WeatherIcons = $AllWeatherIcons
}

Write-Host ""

$SuccessCount = 0
$FailCount = 0

Write-Host "Creating $RemoteDir directory on device..." -ForegroundColor Cyan
try {
    & mpremote connect $ComPort fs mkdir $RemoteDir 2>$null
    Write-Host "✓ $RemoteDir directory ready" -ForegroundColor Green
} catch {
    Write-Host "Note: $RemoteDir directory may already exist" -ForegroundColor Yellow
}

Write-Host ""

foreach ($icon in $WeatherIcons) {
    $LocalIconPath = Join-Path $BaseDir $icon
    if (Test-Path $LocalIconPath) {
        Write-Host "Deploying $icon from $BaseDir..." -ForegroundColor Cyan
        try {
            & mpremote connect $ComPort fs cp $LocalIconPath `:$RemoteDir/$icon
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ $icon deployed successfully" -ForegroundColor Green
                $DeploymentStatus[$icon] = "Success"
                $SuccessCount++
            } else {
                Write-Host "✗ Failed to deploy $icon" -ForegroundColor Red
                $DeploymentStatus[$icon] = "Failed"
                $FailCount++
            }
        } catch {
            Write-Host "✗ Error deploying $icon`: $_" -ForegroundColor Red
            $DeploymentStatus[$icon] = "Error: $_"
            $FailCount++
        }
    } else {
        Write-Host "⚠ $icon not found in $BaseDir" -ForegroundColor Yellow
        $DeploymentStatus[$icon] = "Missing"
        $FailCount++
    }
    
    # Save status after each deployment attempt
    try {
        $DeploymentStatus | ConvertTo-Json | Set-Content $StatusFile
    } catch {
        Write-Host "Warning: Could not save deployment status" -ForegroundColor Yellow
    }
}

# Count already successful icons for summary
$AllSuccessful = $AllWeatherIcons | Where-Object { $DeploymentStatus[$_] -eq "Success" }
$TotalSuccessful = $AllSuccessful.Count

Write-Host ""
Write-Host "Deployment Summary:" -ForegroundColor Green
Write-Host "==================" -ForegroundColor Green

# Count already successful icons for summary
$AllSuccessful = $AllWeatherIcons | Where-Object { $DeploymentStatus[$_] -eq "Success" }
$TotalSuccessful = $AllSuccessful.Count
$PendingIcons = $AllWeatherIcons | Where-Object { $DeploymentStatus[$_] -ne "Success" }

Write-Host "This session: $SuccessCount deployed, $FailCount failed" -ForegroundColor $(if ($FailCount -eq 0) { "Green" } else { "Yellow" })
Write-Host "Total successful: $TotalSuccessful of $($AllWeatherIcons.Count) icons" -ForegroundColor $(if ($TotalSuccessful -eq $AllWeatherIcons.Count) { "Green" } else { "Yellow" })

if ($PendingIcons.Count -gt 0) {
    Write-Host "Remaining icons to deploy: $($PendingIcons.Count)" -ForegroundColor Yellow
    Write-Host "Failed/Missing icons:" -ForegroundColor Yellow
    foreach ($icon in $PendingIcons) {
        $status = if ($DeploymentStatus.ContainsKey($icon)) { $DeploymentStatus[$icon] } else { "Not attempted" }
        Write-Host "  - $icon`: $status" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "Run the script again to retry failed deployments." -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "🎉 All weather icons successfully deployed!" -ForegroundColor Green
    Write-Host "Weather station is ready for use!" -ForegroundColor Green
    
    # Clean up status file when all icons are deployed
    if (Test-Path $StatusFile) {
        Remove-Item $StatusFile -Force
        Write-Host "Cleaned up deployment status file." -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Deployment status saved to: $StatusFile" -ForegroundColor Gray
Write-Host "Use -ForceAll to redeploy all icons regardless of status." -ForegroundColor Gray
Write-Host "Use -BaseDir to specify local icon directory (default: current directory)." -ForegroundColor Gray
Write-Host "Use -RemoteDir to specify remote directory on device (default: res)." -ForegroundColor Gray