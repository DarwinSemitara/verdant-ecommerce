@echo off
echo ========================================
echo Verdant APK Build Script
echo ========================================
echo.

cd finals_app

echo Step 1: Getting dependencies...
call flutter pub get
if errorlevel 1 (
    echo ERROR: Failed to get dependencies
    pause
    exit /b 1
)
echo.

echo Step 2: Generating app icons...
call flutter pub run flutter_launcher_icons
if errorlevel 1 (
    echo WARNING: Icon generation failed, continuing anyway...
)
echo.

echo Step 3: Cleaning previous builds...
call flutter clean
echo.

echo Step 4: Getting dependencies again...
call flutter pub get
echo.

echo Step 5: Building release APK...
call flutter build apk --release
if errorlevel 1 (
    echo ERROR: Build failed
    pause
    exit /b 1
)
echo.

cd ..

echo Step 6: Copying APK to app_build folder...
if not exist "app_build" mkdir app_build
copy "finals_app\build\app\outputs\flutter-apk\app-release.apk" "app_build\verdant-v1.0.0.apk"
if errorlevel 1 (
    echo ERROR: Failed to copy APK
    pause
    exit /b 1
)
echo.

echo ========================================
echo BUILD COMPLETE!
echo ========================================
echo.
echo APK Location: app_build\verdant-v1.0.0.apk
echo.
echo Next steps:
echo 1. Transfer APK to your Android device
echo 2. Install and test
echo 3. Verify app name shows as "Verdant"
echo 4. Verify app icon is correct
echo.
pause
