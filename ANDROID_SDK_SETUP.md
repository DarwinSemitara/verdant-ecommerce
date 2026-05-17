# Android SDK Setup (Without Android Studio)

## Step 1: Download Command-Line Tools

1. Go to: https://developer.android.com/studio#command-line-tools-only
2. Download: **commandlinetools-win-XXXXX_latest.zip** (Windows version)
3. Extract to: `C:\Android\cmdline-tools\latest\`

## Step 2: Set Environment Variables

1. Open System Properties:
   - Press `Win + R`
   - Type: `sysdm.cpl`
   - Press Enter

2. Click "Environment Variables" button

3. Under "System variables", click "New":
   - Variable name: `ANDROID_HOME`
   - Variable value: `C:\Android`

4. Edit "Path" variable, add these entries:
   - `C:\Android\cmdline-tools\latest\bin`
   - `C:\Android\platform-tools`

5. Click OK to save

## Step 3: Install Required SDK Components

Open PowerShell as Administrator and run:

```powershell
# Accept licenses
cd C:\Android\cmdline-tools\latest\bin
.\sdkmanager.bat --licenses

# Install required components
.\sdkmanager.bat "platform-tools"
.\sdkmanager.bat "platforms;android-33"
.\sdkmanager.bat "build-tools;33.0.0"
.\sdkmanager.bat "cmdline-tools;latest"
```

Type `y` and press Enter to accept all licenses.

## Step 4: Verify Installation

Close and reopen PowerShell, then run:

```powershell
flutter doctor
```

Should show:
```
[√] Android toolchain - develop for Android devices
```

## Step 5: Build APK

```powershell
cd C:\Users\PC\Documents\ecomappwtihweb\finals_app
flutter build apk --release
```

APK will be at: `finals_app\build\app\outputs\flutter-apk\app-release.apk`

## Quick Setup Script

Or run this PowerShell script (as Administrator):

```powershell
# Create Android directory
New-Item -ItemType Directory -Path "C:\Android\cmdline-tools\latest" -Force

# Download command-line tools (you need to extract manually)
Write-Host "Download from: https://developer.android.com/studio#command-line-tools-only"
Write-Host "Extract to: C:\Android\cmdline-tools\latest\"
Write-Host ""
Write-Host "After extracting, run:"
Write-Host "cd C:\Android\cmdline-tools\latest\bin"
Write-Host ".\sdkmanager.bat --licenses"
Write-Host ".\sdkmanager.bat 'platform-tools' 'platforms;android-33' 'build-tools;33.0.0'"
```

## Troubleshooting

**If sdkmanager not found**:
- Make sure you extracted to `C:\Android\cmdline-tools\latest\`
- The `bin` folder should be at `C:\Android\cmdline-tools\latest\bin\`

**If ANDROID_HOME not recognized**:
- Close and reopen PowerShell/Command Prompt
- Or restart your computer

**If flutter doctor still shows error**:
- Run: `flutter doctor --android-licenses`
- Accept all licenses

## File Structure Should Look Like:

```
C:\Android\
├── cmdline-tools\
│   └── latest\
│       ├── bin\
│       │   ├── sdkmanager.bat
│       │   └── avdmanager.bat
│       └── lib\
├── platform-tools\
│   └── adb.exe
├── platforms\
│   └── android-33\
└── build-tools\
    └── 33.0.0\
```
