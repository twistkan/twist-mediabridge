param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'vendor'
& $Python -m PyInstaller --noconfirm --windowed --onefile --name TwistMediaBridge --icon assets/twist-mediabridge.ico --add-data "assets;assets" --add-data "companion/TwistContactsBridge.apk;companion" --add-binary "tools/aapt2/aapt2.exe;tools/aapt2" --add-data "tools/aapt2/NOTICE;licenses/aapt2" --add-data "release/licenses;licenses" --add-binary "tools/android/platform-tools/adb.exe;android" --add-binary "tools/android/platform-tools/AdbWinApi.dll;android" --add-binary "tools/android/platform-tools/AdbWinUsbApi.dll;android" --add-data "tools/android/platform-tools/NOTICE.txt;android" --paths vendor --collect-all pillow_heif --collect-all imageio_ffmpeg --collect-all qrcode --collect-all zeroconf --collect-all ifaddr --collect-all cryptography --distpath release --workpath build/media main.py
if ($LASTEXITCODE -ne 0) { throw 'Media build failed' }

