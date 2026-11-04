"""Windows desktop integration without installers or administrator access."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / name


def create_shortcut(executable, desktop=None):
    # JSON carries paths as data; no user path is interpolated into PowerShell code.
    payload = base64.b64encode(json.dumps({'exe': str(Path(executable).resolve()),
                                          'desktop': str(desktop) if desktop else None}).encode()).decode()
    script = """$ErrorActionPreference = 'Stop'
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD')) | ConvertFrom-Json
$desktop = if ($p.desktop) { $p.desktop } else { [Environment]::GetFolderPath('Desktop') }
if (-not $desktop) { throw 'Desktop folder is unavailable' }
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path $desktop 'Twist MediaBridge.lnk'
$exists = Test-Path -LiteralPath $shortcutPath
$link = $shell.CreateShortcut($shortcutPath)
if ($exists -and $link.TargetPath -eq $p.exe -and $link.IconLocation -eq ($p.exe + ',0') -and $link.WorkingDirectory -eq (Split-Path -LiteralPath $p.exe)) { return }
$link.TargetPath = $p.exe
$link.WorkingDirectory = Split-Path -LiteralPath $p.exe
$link.IconLocation = $p.exe + ',0'
$link.Description = 'Twist MediaBridge - your media, connected'
$link.Save()
""".replace('PAYLOAD', payload)
    command = base64.b64encode(script.encode('utf-16le')).decode()
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
                   capture_output=True, check=True, timeout=25,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def ensure_shortcut(home, desktop=None):
    marker = Path(home) / 'desktop-shortcut.json'
    target = str(Path(home) / 'Application' / 'TwistMediaBridge.exe')
    try:
        import shutil
        installed = Path(target)
        installed.parent.mkdir(parents=True, exist_ok=True)
        if Path(sys.executable).resolve() != installed.resolve():
            stage = installed.with_suffix('.new')
            shutil.copy2(sys.executable, stage)
            os.replace(stage, installed)
        # The marker records installation history, not whether the user still
        # has a shortcut. Check the current Windows desktop on every launch.
        if desktop is None:
            create_shortcut(target)
        else:
            create_shortcut(target, desktop)
        marker.write_text(json.dumps({'target': target}), encoding='utf-8')
    except Exception as exc:
        # A managed desktop may forbid shortcuts; launching the app must still work.
        with (Path(home) / 'shortcut-error.log').open('a', encoding='utf-8') as log:
            log.write(str(exc) + '\n')
