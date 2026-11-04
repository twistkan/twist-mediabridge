"""Resolve Android tools without requiring an SDK installation."""
import os
from pathlib import Path
import shutil
from .desktop import resource_path


def resolve_adb(settings=None):
    settings = settings or {}
    custom = settings.get('adb', '')
    if settings.get('adb_mode') == 'custom' and custom and Path(custom).is_file():
        return str(custom)
    # Old settings may contain development paths or a previous one-file
    # extraction directory. They must not override the shipped tools.
    for candidate in (resource_path('android/adb.exe'),
                      resource_path('tools/android/platform-tools/adb.exe')):
        if candidate.is_file():
            return str(candidate)
    for candidate in (custom, shutil.which('adb'),
                      Path(os.environ.get('LOCALAPPDATA', '')) / 'Android/Sdk/platform-tools/adb.exe'):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return ''
