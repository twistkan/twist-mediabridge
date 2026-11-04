"""Deletion entrypoints. UI confirmation is required before calling these functions."""
import shlex
from pathlib import PurePosixPath
from .engine import Android, adb_run, category, check_cancel
from .phone_backup import package_name


def uninstall_apps(phone, packages, cancel, report):
    packages = [package_name(package) for package in packages]
    from .companion_link import Companion
    if isinstance(phone, Companion):
        raise OSError('Uninstalling apps requires USB or Android wireless debugging in this release. You can also uninstall directly on the phone.')
    results = []
    for index, package in enumerate(packages):
        check_cancel(cancel)
        report(index / max(1, len(packages)), 'Uninstalling ' + package)
        try:
            result = adb_run(phone.adb, ['-s', phone.serial, 'uninstall', package], cancel, timeout=180).decode(errors='replace')
            results.append((package, 'Success' in result, result.strip()))
        except OSError as exc:
            results.append((package, False, str(exc)))
    return results


def delete_media(phone, names, cancel, report):
    from .companion_link import Companion
    if not isinstance(phone, Android):
        raise ValueError('Deletion here is available only for files on a connected Android phone.')
    # Validate the whole selection before any file is removed.
    remotes = []
    for name in names:
        if category(name) not in {'Photos', 'Videos'}:
            raise ValueError('Only selected photos and videos may be deleted.')
        remotes.append((name, phone.remote(name)))
    results = []
    for index, (name, remote) in enumerate(remotes):
        check_cancel(cancel)
        report(index / max(1, len(remotes)), 'Deleting ' + name)
        parts = PurePosixPath(remote).parts
        checks = ' && '.join('[ ! -L ' + shlex.quote(str(PurePosixPath(*parts[:i]))) + ' ]' for i in range(3, len(parts)+1))
        quoted = shlex.quote(remote)
        try:
            if isinstance(phone,Companion):
                success=phone.call('delete_media',cancel,path=remote) is True
                results.append((name,success,'Deleted' if success else 'File not deleted. Check write access to this folder on the phone.'))
                continue
            phone.shell(f'{checks} && [ -f {quoted} ] && rm -- {quoted} && [ ! -e {quoted} ]', cancel)
            results.append((name, True, 'Deleted'))
        except OSError as exc:
            results.append((name, False, str(exc)))
    return results
