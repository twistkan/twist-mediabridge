from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

CATEGORIES = ('Photos', 'Videos', 'Music', 'Documents', 'Other files')
SHARED_ROOTS = ('DCIM', 'Pictures', 'Movies', 'Music', 'Documents', 'Download', 'Android/media')
EXTENSIONS = {
    'Photos': {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.dng', '.bmp'},
    'Videos': {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.3gp', '.m4v'},
    'Music': {'.mp3', '.m4a', '.wav', '.flac', '.aac', '.ogg', '.opus'},
    'Documents': {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv', '.ppt', '.pptx', '.epub'},
}


class Cancelled(Exception):
    pass


class PartialScanOutput(bytes):
    """Complete filename records retained when a read-only scan times out."""


def check_cancel(cancel):
    if cancel and cancel.is_set():
        raise Cancelled('Cancelled. Completed files are retained; unfinished backup is not restorable.')


def category(name):
    suffix = Path(name).suffix.lower()
    return next((k for k, extensions in EXTENSIONS.items() if suffix in extensions), 'Other files')


def digest(path, cancel=None):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        while chunk := handle.read(1024 * 1024):
            check_cancel(cancel)
            h.update(chunk)
    return h.hexdigest()


def safe_relative(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid file path in backup or device listing.')
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise ValueError('Unsafe relative path.')
    for part in p.parts:
        if re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((' ', '.')):
            raise ValueError('File name cannot be safely represented on Windows.')
        if part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            raise ValueError('Reserved Windows file name.')
    return p


def contained(root, name):
    root = Path(root).resolve()
    p = root.joinpath(*safe_relative(name).parts)
    if not p.resolve().is_relative_to(root):
        raise ValueError('Path escapes the selected folder.')
    # Junctions/reparse points can redirect writes outside the selected tree.
    for segment in (p, *p.parents):
        if segment == root:
            break
        if segment.is_symlink() or (hasattr(segment, 'is_junction') and segment.is_junction()):
            raise ValueError('Links and junctions are not supported.')
    return p


def overlap(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a.is_relative_to(b) or b.is_relative_to(a)


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def copy_new(source, destination, cancel=None):
    """Copy without overwriting an existing destination; publish only after verification."""
    source, destination = Path(source), Path(destination)
    expected = digest(source, cancel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and digest(destination, cancel) == expected:
            return expected, 'already present'
        raise FileExistsError('Different content already exists at the destination. Nothing was overwritten.')
    fd, temp_name = tempfile.mkstemp(prefix='.devicebridge-', dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, 'wb') as out, open(source, 'rb') as inp:
            while chunk := inp.read(1024 * 1024):
                check_cancel(cancel)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if digest(temp, cancel) != expected:
            raise OSError('Copied file failed SHA-256 verification.')
        check_cancel(cancel)
        # Windows rename refuses to overwrite an existing file (including a race).
        if os.name == 'nt':
            os.rename(temp, destination)
        else:
            os.link(temp, destination)
            temp.unlink()
        return expected, 'copied'
    finally:
        temp.unlink(missing_ok=True)


class Folder:
    kind = 'folder'

    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError('Choose an existing folder.')
        self.key = str(self.root).casefold()
        self.label = f'Folder · {self.root}'

    def files(self, selected, cancel):
        for current, dirs, files in os.walk(self.root, onerror=lambda e: (_ for _ in ()).throw(e), followlinks=False):
            check_cancel(cancel)
            for name in dirs:
                p = Path(current) / name
                if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                    raise ValueError('Folder contains a link/junction. Choose a folder without links.')
            for name in files:
                relative = (Path(current) / name).relative_to(self.root).as_posix()
                p = contained(self.root, relative)
                if p.is_symlink():
                    raise ValueError('Symbolic links are not supported.')
                if category(relative) in selected:
                    yield relative, p.stat().st_size

    def read(self, name, temp, cancel):
        check_cancel(cancel)
        return contained(self.root, name)

    def write(self, source, name, cancel):
        return copy_new(source, contained(self.root, name), cancel)


def adb_run(adb, args, cancel=None, timeout=180, partial_on_timeout=False, input_data=None):
    creation = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([str(adb), *args], stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                                stdout=out, stderr=err, creationflags=creation)
        try:
            if input_data is not None:
                proc.stdin.write(input_data)
                proc.stdin.close()
            import time
            started = time.monotonic()
            while proc.poll() is None:
                check_cancel(cancel)
                if time.monotonic() - started > timeout:
                    if partial_on_timeout:
                        proc.kill()
                        proc.wait()
                        out.seek(0)
                        data = out.read()
                        boundary = data.rfind(b'\0')
                        return PartialScanOutput(data[:boundary + 1] if boundary >= 0 else b'')
                    raise TimeoutError('Android command timed out. Check the USB or Wi-Fi connection and unlock your phone.')
                threading.Event().wait(.1)
            out.seek(0)
            err.seek(0)
            output = out.read()
            if proc.returncode:
                detail = err.read().decode('utf-8', errors='replace').strip()
                raise OSError('Android command failed. Check authorization, storage and the USB or Wi-Fi connection. ' + detail[-250:])
            return output
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def discover(adb):
    output = adb_run(adb, ['devices', '-l'], timeout=20).decode('utf-8', errors='replace')
    ready, blocked = [], []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2:
            continue
        serial, state = fields[:2]
        if state == 'device':
            model = next((f[6:] for f in fields[2:] if f.startswith('model:')), 'Android')
            ready.append(Android(adb, serial, model.replace('_', ' ')))
        else:
            blocked.append(state)
    return ready, blocked


class Android:
    kind = 'android'

    def __init__(self, adb, serial, model='Android'):
        self.adb, self.serial = str(adb), serial
        self.key = 'android:' + serial
        self.label = f'{model} · Android · {serial}'

    def shell(self, script, cancel):
        return adb_run(self.adb, ['-s', self.serial, 'shell', script], cancel)

    def remote(self, name):
        safe_relative(name)
        if not any(name.startswith(root + '/') for root in SHARED_ROOTS):
            raise ValueError('Android access is limited to common shared-storage folders.')
        return '/sdcard/' + name

    def destination_name(self, name):
        parts = safe_relative(name).parts
        if any(name.startswith(root + '/') for root in SHARED_ROOTS):
            return name
        folder = {'Photos': 'Pictures', 'Videos': 'Movies', 'Music': 'Music', 'Documents': 'Documents'}.get(category(name), 'Download')
        return f'{folder}/DeviceBridge/{name}'

    def files(self, selected, cancel):
        script = 'for d in DCIM Pictures Movies Music Documents Download Android/media; do if [ -d "/sdcard/$d" ]; then find "/sdcard/$d" -type f -print0 || exit 1; fi; done'
        output = self.shell(script, cancel)
        for raw in output.split(b'\0'):
            if not raw:
                continue
            name = raw.decode('utf-8').removeprefix('/sdcard/')
            if category(name) in selected:
                self.remote(name)
                yield name, None

    def media_files(self, cancel, report):
        """Read independent roots so one app folder or bad name cannot erase the library."""
        self.scan_warnings = []
        skipped = 0
        for index, root in enumerate(SHARED_ROOTS):
            check_cancel(cancel)
            report(index / len(SHARED_ROOTS), f'Reading {root} albums…')
            remote = '/sdcard/' + root
            script = f'if [ -d {shlex.quote(remote)} ]; then find {shlex.quote(remote)} -type f -print0 2>/dev/null; code=$?; printf "\\000__DEVICEBRIDGE_STATUS__%s\\000" "$code"; fi'
            try:
                output = adb_run(self.adb, ['-s', self.serial, 'shell', script], cancel, timeout=15, partial_on_timeout=True)
            except Cancelled:
                raise
            except (OSError, TimeoutError) as exc:
                self.scan_warnings.append(f'{root}: could not read this folder')
                continue
            if isinstance(output, PartialScanOutput):
                self.scan_warnings.append(f'{root}: time limit reached; partial results shown')
            for raw in output.split(b'\0'):
                if not raw:
                    continue
                if raw.startswith(b'__DEVICEBRIDGE_STATUS__'):
                    if raw != b'__DEVICEBRIDGE_STATUS__0':
                        self.scan_warnings.append(f'{root}: some subfolders were inaccessible')
                    continue
                try:
                    name = raw.decode('utf-8').removeprefix('/sdcard/')
                    if category(name) not in {'Photos', 'Videos'}:
                        continue
                    self.remote(name)
                except (UnicodeError, ValueError):
                    skipped += 1
                    continue
                if any(part.startswith('.') for part in PurePosixPath(name).parts):
                    continue
                yield name, None
        if skipped:
            self.scan_warnings.append(f'{skipped} media files skipped because their names are unsupported on Windows')

    def remote_digest(self, path, cancel):
        value = self.shell('sha256sum ' + shlex.quote(path), cancel).decode().split()[0]
        if not re.fullmatch('[0-9a-f]{64}', value):
            raise OSError('Phone does not provide a usable SHA-256 verification command.')
        return value

    def read(self, name, temp, cancel):
        remote = self.remote(name)
        expected = self.remote_digest(remote, cancel)
        local = Path(temp) / 'incoming'
        local.unlink(missing_ok=True)
        adb_run(self.adb, ['-s', self.serial, 'pull', remote, str(local)], cancel, timeout=3600)
        if digest(local, cancel) != expected:
            raise OSError('Phone file changed during reading or failed checksum verification.')
        return local

    def write(self, source, name, cancel):
        remote = self.remote(self.destination_name(name))
        expected = digest(source, cancel)
        quoted = shlex.quote(remote)
        # Reject links below /sdcard. The /sdcard mount alias itself is expected.
        parts = PurePosixPath(remote).parts
        paths = [str(PurePosixPath(*parts[:i])) for i in range(3, len(parts) + 1)]
        self.shell(' && '.join('[ ! -L ' + shlex.quote(p) + ' ]' for p in paths), cancel)
        exists = self.shell(f'if [ -e {quoted} ]; then echo yes; else echo no; fi', cancel).strip()
        if exists == b'yes':
            if self.remote_digest(remote, cancel) == expected:
                return expected, 'already present'
            raise FileExistsError('Destination phone already has different content at this path.')
        parent = str(PurePosixPath(remote).parent)
        stage = parent + '/.devicebridge-' + uuid.uuid4().hex
        self.shell('mkdir -p ' + shlex.quote(parent), cancel)
        try:
            adb_run(self.adb, ['-s', self.serial, 'push', str(source), stage], cancel, timeout=3600)
            if self.remote_digest(stage, cancel) != expected:
                raise OSError('Phone write failed checksum verification.')
            check_cancel(cancel)
            # ln atomically refuses replacement; no source/target data is erased.
            # Shared storage often lacks hard links, so use mv -n and verify stage removal.
            script = f'mv -nT {shlex.quote(stage)} {quoted} && [ ! -e {shlex.quote(stage)} ]'
            self.shell(script, cancel)
            if self.remote_digest(remote, cancel) != expected:
                raise OSError('Final phone file failed verification.')
            return expected, 'copied'
        finally:
            try:
                self.shell('rm -f ' + shlex.quote(stage), None)
            except OSError:
                pass


def load_manifest(folder):
    root = Path(folder).resolve()
    file = root / 'manifest.json'
    if file.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Backup manifest is too large.')
    data = json.loads(file.read_text(encoding='utf-8'))
    if data.get('format') != 'devicebridge-1' or data.get('status') != 'complete' or not isinstance(data.get('items'), list):
        raise ValueError('This is not a completed DeviceBridge backup.')
    seen = set()
    for item in data['items']:
        name = item['path']
        safe_relative(name)
        if name.casefold() in seen:
            raise ValueError('Duplicate paths in backup.')
        seen.add(name.casefold())
        contained(root / 'files', name)
        if not isinstance(item['size'], int) or item['size'] < 0 or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
            raise ValueError('Invalid backup file metadata.')
        if item['category'] != category(name):
            raise ValueError('Invalid category in backup.')
    return data


def backup(source, library, selected, cancel, report):
    library = Path(library).resolve()
    if isinstance(source, Folder) and overlap(source.root, library):
        raise ValueError('Backup library must be outside the source folder.')
    library.mkdir(parents=True, exist_ok=True)
    folder = library / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir()
    manifest = {'format': 'devicebridge-1', 'status': 'incomplete', 'source': source.label,
                'created': datetime.now(timezone.utc).isoformat(), 'items': []}
    atomic_json(folder / 'manifest.json', manifest)
    report(0, 'Scanning supported files…')
    try:
        files = list(source.files(selected, cancel))
        if not files:
            raise ValueError('No files match the selected categories.')
        if len({name.casefold() for name, _ in files}) != len(files):
            raise ValueError('Source contains names differing only by letter case; Windows cannot preserve both.')
        needed = sum(size or 0 for _, size in files)
        if needed > shutil.disk_usage(library).free:
            raise OSError('Not enough free space for this backup.')
        with tempfile.TemporaryDirectory(prefix='devicebridge-') as temp:
            for index, (name, _) in enumerate(files):
                check_cancel(cancel)
                report(index / len(files), f'Backing up {index + 1} of {len(files)} · {name}')
                local = source.read(name, temp, cancel)
                target = contained(folder / 'files', name)
                checksum, _ = copy_new(local, target, cancel)
                manifest['items'].append({'path': name, 'category': category(name), 'size': target.stat().st_size, 'sha256': checksum})
        check_cancel(cancel)
        manifest['status'] = 'complete'
        atomic_json(folder / 'manifest.json', manifest)
        report(1, f'Backup verified · {len(files)} files')
        return {'status': 'complete', 'copied': len(files), 'failed': 0, 'folder': str(folder)}
    except Exception:
        atomic_json(folder / 'manifest.json', manifest)
        raise


def transfer(source, target, selected, cancel, report, backup_folder=None, paths=None, flatten=False):
    if flatten and (not isinstance(target,Folder) or backup_folder):
        raise ValueError('Flat export is available only for ordinary exports to a PC folder.')
    if source.key == target.key:
        raise ValueError('Source and destination must be different.')
    if isinstance(source, Folder) and isinstance(target, Folder) and overlap(source.root, target.root):
        raise ValueError('Source and destination folders must not contain each other.')
    manifest = load_manifest(backup_folder) if backup_folder else None
    report(0, 'Checking selected files…')
    if manifest:
        records = [i for i in manifest['items'] if i['category'] in selected]
        # Preflight ALL selected backup files before writing any target files.
        for item in records:
            check_cancel(cancel)
            p = contained(source.root, item['path'])
            if p.stat().st_size != item['size'] or digest(p, cancel) != item['sha256']:
                raise ValueError('Backup integrity check failed. No restore was started.')
        files = [(i['path'], i['size']) for i in records]
    elif paths is not None:
        files = []
        for name in sorted(set(paths)):
            safe_relative(name)
            if category(name) in selected:
                files.append((name, None))
    else:
        files = list(source.files(selected, cancel))
    if not files:
        raise ValueError('No files match the selected categories.')
    result = {'status': 'complete', 'requested':len(files), 'copied': 0, 'present': 0, 'failed': 0, 'errors': [], 'items':[]}
    with tempfile.TemporaryDirectory(prefix='devicebridge-') as temp:
        for index, (name, _) in enumerate(files):
            check_cancel(cancel)
            report(index / len(files), f'Copying {index + 1} of {len(files)} · {name}')
            local = None
            destination_name=PurePosixPath(name).name if flatten else name
            try:
                local = source.read(name, temp, cancel)
                checksum, state = target.write(local, destination_name, cancel)
                result['present' if state == 'already present' else 'copied'] += 1
                result['items'].append({'path':name,'destination':destination_name,'status':state,'sha256':checksum})
            except Cancelled:
                raise
            except (OSError, ValueError) as exc:
                result['failed'] += 1
                result['errors'].append({'path': name, 'error': str(exc)})
                result['items'].append({'path':name,'destination':destination_name,'status':'failed','error':str(exc)})
            finally:
                # Companion reads use unique staging names. Keep batch disk use bounded
                # to one incoming file, and never remove a source-folder original.
                if local is not None and not isinstance(source,Folder):
                    staged=Path(local)
                    if staged.resolve().is_relative_to(Path(temp).resolve()):
                        try:staged.unlink(missing_ok=True)
                        except OSError:pass
    if result['failed']:
        result['status'] = 'partial'
    report(1, f"{result['copied']} copied · {result['present']} already present · {result['failed']} failed")
    return result
