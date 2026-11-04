"""Explicit vCard-file and installed APK backup; never accesses private app data."""
from pathlib import Path
import json
import re
import shlex
import tempfile
import uuid
import zipfile
from datetime import datetime
from .engine import adb_run, digest, copy_new, atomic_json, contained, check_cancel


def package_name(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', value):
        raise ValueError('Invalid Android package name')
    return value


def list_apps(phone, cancel):
    output = phone.shell('pm list packages -3', cancel).decode()
    return sorted(package_name(line[8:].strip()) for line in output.splitlines() if line.startswith('package:'))


def list_app_details(phone, cancel, report, cache_file, on_batch=None):
    from .companion_link import Companion
    if isinstance(phone,Companion):
        rows=phone.call('apps',cancel)
        for row in rows:package_name(row['id'])
        return sorted(rows,key=lambda row:row['name'].casefold())
    from .app_labels import app_label
    import zipfile
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        cache = json.loads(Path(cache_file).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        cache = {}
    output = phone.shell('pm list packages -3 -f', cancel).decode()
    entries = [line[8:].rsplit('=', 1) for line in output.splitlines() if line.startswith('package:') and '=' in line]
    rows = []
    def read(entry):
        apk, package = entry
        package_name(package)
        key = phone.key + ':' + apk
        label = cache.get(key)
        if not label:
            try:
                label = app_label(phone, apk, cancel)
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                label = None
        return {'id': package, 'name': label or package, 'detail': package, 'label_available': bool(label)}, key
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(read, entry) for entry in entries]
        for future in as_completed(futures):
            check_cancel(cancel)
            row, key = future.result()
            rows.append(row)
            if row['label_available']:
                cache[key] = row['name']
            report(len(rows) / max(1, len(entries)), f'Reading app names: {len(rows)}/{len(entries)}')
            if on_batch:
                on_batch(sorted(rows, key=lambda item: item['name'].casefold()))
    atomic_json(Path(cache_file), cache)
    return sorted(rows, key=lambda item: item['name'].casefold())


def parse_vcards(raw):
    import hashlib
    cards = re.findall(rb'(?im)^BEGIN:VCARD\r?\n.*?^END:VCARD[^\S\r\n]*(?:\r?\n|$)', raw, re.DOTALL)
    rows = []
    for card in cards:
        text = re.sub(r'\r?\n[ \t]', '', card.decode('utf-8-sig', errors='replace'))
        match = re.search(r'(?im)^FN(?:;[^:]*)?:(.*)$', text)
        name = match.group(1).strip().replace('\\,', ',').replace('\\n', ' ') if match else 'Unnamed contact'
        numbers = re.findall(r'(?im)^TEL(?:;[^:]*)?:(.*)$', text)
        rows.append({'id': hashlib.sha256(card).hexdigest(), 'name': name,
                     'detail': ' · '.join(number.strip() for number in numbers), 'card': card})
    return rows


def load_contact_details(phone, cancel, report):
    from .contacts_bridge import load_contacts
    from .companion_link import Companion
    if isinstance(phone,Companion):
        return load_contacts(phone,cancel,report)
    try:
        return load_contacts(phone, cancel, report)
    except OSError as exc:
        live_error = exc
    rows = {}
    files = list_vcards(phone, cancel)
    if not files:
        raise live_error
    with tempfile.TemporaryDirectory(prefix='twist-contacts-') as temp:
        for index, remote in enumerate(files):
            check_cancel(cancel)
            report(index / max(1, len(files)), 'Reading exported contacts…')
            local = Path(temp) / 'contacts.vcf'
            expected = phone.remote_digest(remote, cancel)
            adb_run(phone.adb, ['-s', phone.serial, 'pull', remote, str(local)], cancel)
            if digest(local, cancel) != expected:
                raise ValueError('Contacts export changed while reading. Export again and retry.')
            for row in parse_vcards(local.read_bytes()):
                rows[row['id']] = row
    return sorted(rows.values(), key=lambda item: item['name'].casefold())


def save_selected_contacts(rows, destination, cancel, phone=None, report=lambda *args: None, on_saved=None):
    if not rows:
        raise ValueError('Select at least one contact.')
    with tempfile.TemporaryDirectory() as temp:
        local = Path(temp) / 'selected.vcf'
        report(0, f'Preparing {len(rows)} contacts for vCard backup…')
        from .contacts_bridge import read_vcard, export_vcards
        with local.open('wb') as output:
            if all(row.get('live') for row in rows):
                for chunk in export_vcards(phone, rows, cancel, report):
                    output.write(chunk.rstrip(b'\r\n') + b'\r\n')
            else:
                for index, row in enumerate(rows):
                    check_cancel(cancel)
                    card = read_vcard(phone, row, cancel) if row.get('live') else row['card']
                    output.write(card.rstrip(b'\r\n') + b'\r\n')
                    report((index+1)/len(rows), f'Exported {index+1} of {len(rows)} contacts')
        validate_vcard(local)
        report(1, 'Verifying and saving vCard backup…')
        copy_new(local, destination, cancel)
    if on_saved:
        on_saved(destination)
    return f'Saved {len(rows)} selected contacts as vCard.'


def contact_backup_name(now=None):
    return 'Contacts_' + (now or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')


def save_individual_contacts(rows, destination, cancel, phone=None, report=lambda *args: None, on_saved=None):
    """Stage complete native cards, then publish one named file per selected contact."""
    from .engine import safe_relative
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.twist-contacts-', dir=destination) as temp:
        temp = Path(temp)
        combined = temp / 'combined.vcf'
        save_selected_contacts(rows, combined, cancel, phone, lambda value, text: report(value * .85, text))
        cards = re.findall(rb'(?im)^BEGIN:VCARD\r?\n.*?^END:VCARD[^\S\r\n]*(?:\r?\n|$)', combined.read_bytes(), re.DOTALL)
        if len(cards) != len(rows):
            raise ValueError('Contact export count did not match selection. No individual backup was published.')
        stage = temp / 'contacts'
        stage.mkdir()
        used = set()
        for index, (row, card) in enumerate(zip(rows, cards)):
            check_cancel(cancel)
            stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', row.get('name') or 'Unnamed contact').strip(' .')[:100] or 'Unnamed contact'
            try:
                safe_relative(stem)
            except ValueError:
                stem = 'Contact-' + stem
            filename = stem + '.vcf'
            number = 2
            while filename.casefold() in used:
                filename = f'{stem} ({number}).vcf'
                number += 1
            used.add(filename.casefold())
            file = stage / filename
            file.write_bytes(card.rstrip(b'\r\n') + b'\r\n')
            if validate_vcard(file) != 1:
                raise ValueError('Individual contact file validation failed.')
            report(.85 + .15 * (index+1)/len(rows), f'Saved {index+1} of {len(rows)} individual vCards')
        check_cancel(cancel)
        folder = destination / contact_backup_name()
        number = 2
        while folder.exists():
            folder = destination / (contact_backup_name() + f' ({number})')
            number += 1
        stage.rename(folder)
    if on_saved:
        on_saved(folder)
    return f'Saved {len(rows)} individual vCard files in:\n{folder}'


def backup_app(phone, package, destination, cancel, report):
    package_name(package)
    from .companion_link import Companion
    if isinstance(phone,Companion):
        rows=phone.call('app_files',cancel,package=package)
        if not rows or len(rows)>500:raise ValueError('Invalid APK file list')
        folder=Path(destination)/(package+'-'+uuid.uuid4().hex[:8])
        folder.mkdir(parents=True)
        manifest={'format':'twist-apks-1','package':package,'status':'incomplete','files':[]}
        atomic_json(folder/'app.json',manifest)
        with tempfile.TemporaryDirectory() as temp:
            for index,row in enumerate(rows):
                report(index/len(rows),'Backing up '+package)
                local=phone.read(row['path'],temp,cancel)
                target=folder/f'{index:03}.apk'
                expected,_=copy_new(local,target,cancel)
                local.unlink(missing_ok=True)
                manifest['files'].append({'name':target.name,'sha256':expected})
        manifest['status']='complete'
        atomic_json(folder/'app.json',manifest)
        return folder
    paths = [line[8:].strip() for line in phone.shell('pm path ' + shlex.quote(package), cancel).decode().splitlines() if line.startswith('package:')]
    if not paths or any(not p.startswith('/') or not p.endswith('.apk') or '\n' in p for p in paths):
        raise ValueError('Android did not return readable APK files for this app.')
    folder = Path(destination) / (package + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    manifest = {'format': 'twist-apks-1', 'package': package, 'status': 'incomplete', 'files': []}
    atomic_json(folder / 'app.json', manifest)
    for index, remote in enumerate(paths):
        check_cancel(cancel)
        report(index / len(paths), 'Backing up ' + package)
        target = folder / f'{index:03}.apk'
        expected = phone.remote_digest(remote, cancel)
        adb_run(phone.adb, ['-s', phone.serial, 'pull', remote, str(target)], cancel)
        if digest(target, cancel) != expected:
            raise ValueError('App changed during backup; please retry.')
        manifest['files'].append({'name': target.name, 'sha256': expected})
    manifest['status'] = 'complete'
    atomic_json(folder / 'app.json', manifest)
    return folder


def backup_app_file(phone, package, display_name, destination, cancel, report):
    from .engine import safe_relative
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', display_name).strip(' .')[:120] or package
    try:
        safe_relative(stem)
    except ValueError:
        stem = 'App-' + stem
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='twist-apk-export-') as temp:
        folder = backup_app(phone, package, temp, cancel, report)
        manifest = json.loads((folder / 'app.json').read_text(encoding='utf-8'))
        manifest['name'] = display_name
        files = manifest['files']
        if len(files) == 1:
            output = destination / (stem + '.apk')
            source = folder / files[0]['name']
        else:
            output = destination / (stem + '.apks')
            source = Path(temp) / 'export.apks'
            with zipfile.ZipFile(source, 'w', compression=zipfile.ZIP_STORED) as archive:
                for index, item in enumerate(files):
                    check_cancel(cancel)
                    archive_name = 'base.apk' if index == 0 else f'split-{index:03}.apk'
                    archive.write(folder / item['name'], archive_name)
                    item['name'] = archive_name
                archive.writestr('app.json', json.dumps(manifest))
                archive.writestr('HOW-TO-RESTORE.txt', 'Open Twist MediaBridge > Apps > Reinstall file, then select this .apks archive. All required APK parts are included. Android checks device compatibility.\n')
        if output.exists() and digest(source, cancel) != digest(output, cancel):
            output = output.with_name(output.stem + '-' + uuid.uuid4().hex[:6] + output.suffix)
        copy_new(source, output, cancel)
    return output


def restore_app_file(phone, source, cancel, report):
    from .companion_link import Companion
    source = Path(source)
    if source.is_dir():
        return restore_app(phone, source, cancel, report)
    if source.suffix.lower() == '.apk':
        if isinstance(phone, Companion):
            return phone.install_apks([source], cancel, report)
        report(0, 'Installing ' + source.name)
        output = adb_run(phone.adb, ['-s', phone.serial, 'install', '-r', str(source)], cancel, timeout=600).decode(errors='replace')
        if 'Success' not in output:
            raise ValueError(output or 'Android did not confirm installation.')
        return 'Installed ' + source.name
    if source.suffix.lower() != '.apks':
        raise ValueError('Select an .apk or .apks backup file.')
    with tempfile.TemporaryDirectory(prefix='twist-apks-restore-') as temp, zipfile.ZipFile(source) as archive:
        folder = Path(temp)
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate entries in app archive.')
        if archive.getinfo('app.json').file_size > 1024*1024:
            raise ValueError('Invalid app manifest size.')
        data = json.loads(archive.read('app.json'))
        files = data.get('files', [])
        if not files or len(files) > 500:
            raise ValueError('Invalid app archive file list.')
        total = 0
        for item in files:
            target = contained(folder, item['name'])
            entry = archive.getinfo(item['name'])
            total += entry.file_size
            if total > 8*1024**3:
                raise ValueError('App archive exceeds size limit.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as src, target.open('wb') as out:
                while chunk := src.read(1024*1024):
                    check_cancel(cancel)
                    out.write(chunk)
        atomic_json(folder / 'app.json', data)
        return restore_app(phone, folder, cancel, report)


def restore_app(phone, folder, cancel, report):
    from .companion_link import Companion
    folder = Path(folder)
    data = json.loads((folder / 'app.json').read_text(encoding='utf-8'))
    if data.get('format') != 'twist-apks-1' or data.get('status') != 'complete':
        raise ValueError('Select a completed Twist app backup.')
    package_name(data['package'])
    files = data.get('files', [])
    if not files or len(files) > 500:
        raise ValueError('Invalid APK backup file list.')
    paths = []
    for item in files:
        path = contained(folder, item['name'])
        if path.suffix != '.apk' or digest(path, cancel) != item['sha256']:
            raise ValueError('APK backup integrity check failed.')
        paths.append(str(path))
    if isinstance(phone, Companion):
        return phone.install_apks(paths, cancel, report)
    report(0, 'Installing ' + data['package'])
    output = adb_run(phone.adb, ['-s', phone.serial, 'install-multiple', '-r', *paths], cancel, timeout=600).decode(errors='replace')
    if 'Success' not in output:
        raise ValueError(output or 'Android did not confirm installation.')
    return 'Installed ' + data['package']


def list_vcards(phone, cancel):
    output = phone.shell("find /sdcard/ -maxdepth 4 -type f -iname '*.vcf' -print 2>/dev/null; true", cancel).decode()
    return sorted(p for p in output.splitlines() if p.startswith('/sdcard/') and p.lower().endswith('.vcf'))


def validate_vcard(path):
    raw = Path(path).read_bytes()
    text = raw.decode('utf-8-sig', errors='replace').upper()
    count = text.count('BEGIN:VCARD')
    if not count or count != text.count('END:VCARD'):
        raise ValueError('This file does not contain complete vCard contacts.')
    return count


def backup_vcard(phone, remote, destination, cancel):
    if not remote.startswith('/sdcard/') or not remote.lower().endswith('.vcf') or '\n' in remote:
        raise ValueError('Choose an exported vCard in shared phone storage.')
    with tempfile.TemporaryDirectory() as temp:
        local = Path(temp) / 'contacts.vcf'
        expected = phone.remote_digest(remote, cancel)
        adb_run(phone.adb, ['-s', phone.serial, 'pull', remote, str(local)], cancel)
        if digest(local, cancel) != expected:
            raise ValueError('Contacts file changed while copying.')
        count = validate_vcard(local)
        copy_new(local, Path(destination), cancel)
    return f'Backed up {count} contacts as vCard.'


def restore_vcard(phone, local, cancel):
    count = validate_vcard(local)
    name = 'Download/TwistMediaBridge/contacts-' + uuid.uuid4().hex[:8] + '.vcf'
    phone.write(Path(local), name, cancel)
    return f'{count} contacts copied to {name}. On your phone, open Contacts > Manage contacts > Import, and select this file. Contacts have not been imported yet.'
