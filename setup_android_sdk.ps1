# Android SDK Setup Script
# Run as Administrator

Write-Host "=== Android SDK Setup ===" -ForegroundColor Green
Write-Host ""

# Step 1: Create directory
Write-Host "Step 1: Creating Android directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path "C:\Android\cmdline-tools\latest" -Force | Out-Null
Write-Host "✓ Directory created: C:\Android\cmdline-tools\latest" -ForegroundColor Green
Write-Host ""

# Step 2: Download instructions
Write-Host "Step 2: Download Command-Line Tools" -ForegroundColor Yellow
Write-Host "1. Open this link in your browser:" -ForegroundColor Cyan
Write-Host "   https://developer.android.com/studio#command-line-tools-only" -ForegroundColor White
Write-Host ""
Write-Host "2. Download: commandlinetools-win-XXXXX_latest.zip" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Extract the ZIP file" -ForegroundColor Cyan
Write-Host "   - Inside the ZIP, you'll find a 'cmdline-tools' folder" -ForegroundColor White
Write-Host "   - Copy everything from that folder to:" -ForegroundColor White
Write-Host "     C:\Android\cmdline-tools\latest\" -ForegroundColor White
Write-Host ""

# Step 3: Set environment variables
Write-Host "Step 3: Setting Environment Variables..." -ForegroundColor Yellow
try {
    [Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Android", "Machine")
    
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $newPaths = @(
        "C:\Android\cmdline-tools\latest\bin",
        "C:\Android\platform-tools"
    )
    
    foreach ($newPath in $newPaths) {
        if ($currentPath -notlike "*$newPath*") {
            $currentPath = "$currentPath;$newPath"
        }
    }
    
    [Environment]::SetEnvironmentVariable("Path", $currentPath, "Machine")
    Write-Host "✓ Environment variables set" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to set environment variables. Run as Administrator!" -ForegroundColor Red
}
Write-Host ""

# Step 4: Next steps
Write-Host "Step 4: After extracting the tools, run these commands:" -ForegroundColor Yellow
Write-Host ""
Write-Host "cd C:\Android\cmdline-tools\latest\bin" -ForegroundColor Cyan
Write-Host ".\sdkmanager.bat --licenses" -ForegroundColor Cyan
Write-Host ".\sdkmanager.bat 'platform-tools' 'platforms;android-33' 'build-tools;33.0.0'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Then verify with:" -ForegroundColor Yellow
Write-Host "flutter doctor" -ForegroundColor Cyan
Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host "Remember to close and reopen PowerShell after setting environment variables!" -ForegroundColor Yellow
