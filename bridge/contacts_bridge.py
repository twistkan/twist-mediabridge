"""Permission-based live contacts access through the bundled Android companion."""
import base64
import json
import re
import shlex
from urllib.parse import urlencode
from .engine import adb_run, check_cancel
from .desktop import resource_path

AUTHORITY = 'content://com.twist.mediabridge.contacts'


def payload(phone, path, cancel):
    from .companion_link import Companion
    if isinstance(phone, Companion):
        from urllib.parse import urlsplit, parse_qs
        uri = urlsplit(path)
        args = {key: values[0] for key, values in parse_qs(uri.query).items()}
        if uri.path.startswith('/vcard/'):
            return base64.b64decode(phone.call('vcard',cancel,contact_id=uri.path.split('/')[-1],lookup=args['lookup']),validate=True)
        return json.dumps(phone.call('contacts',cancel,offset=int(args.get('offset',0)))).encode()
    output = phone.shell('content query --uri ' + shlex.quote(AUTHORITY + path), cancel).decode('utf-8', errors='replace')
    match = re.search(r'payload=([A-Za-z0-9+/=]+)', output)
    if not match:
        raise OSError('Phone contacts access is not ready. Click Enable contacts, open Twist Contacts Bridge on your phone and allow Contacts access. Then click Load contacts.')
    return base64.b64decode(match.group(1), validate=True)


def load_contacts(phone, cancel, report):
    rows = []
    offset = 0
    while True:
        check_cancel(cancel)
        values = json.loads(payload(phone, '/contacts?' + urlencode({'offset': offset}), cancel))
        for value in values:
            contact_id = str(value['contact_id'])
            if not contact_id.isdigit():
                raise ValueError('Invalid contact ID returned by phone')
            rows.append({'id': 'live:' + contact_id, 'contact_id': contact_id,
                         'lookup': value['lookup'], 'name': value.get('name') or 'Unnamed contact',
                         'detail': ' · '.join(value.get('numbers', [])), 'live': True})
        report(0, f'Reading phone contacts: {len(rows):,}')
        if len(values) < 200:
            break
        offset += len(values)
    return sorted(rows, key=lambda row: row['name'].casefold())


def contact_path(row, kind='contacts'):
    value = row.get('contact_id', '')
    if not row.get('live') or not str(value).isdigit() or not row.get('lookup'):
        raise ValueError('Only live phone contacts can be deleted or read. Load phone contacts first.')
    return '/' + kind + '/' + str(value) + '?' + urlencode({'lookup': row['lookup']})


def read_vcard(phone, row, cancel):
    return payload(phone, contact_path(row, 'vcard'), cancel)


def export_vcards(phone, rows, cancel, report):
    from .companion_link import Companion
    if isinstance(phone, Companion):
        for index, row in enumerate(rows):
            check_cancel(cancel)
            raw = read_vcard(phone, row, cancel)
            if len(re.findall(rb'(?im)^BEGIN:VCARD\s*$',raw)) != 1 or len(re.findall(rb'(?im)^END:VCARD\s*$',raw)) != 1:
                raise OSError('Incomplete phone contact export')
            yield raw.rstrip(b'\r\n') + b'\r\n'
            report((index+1)/len(rows),f'Exported {index+1} of {len(rows)} contacts')
        return
    total = len(rows)
    report(0, f'Exporting {total} contacts…')
    for start in range(0, total, 10):
        check_cancel(cancel)
        selected = rows[start:start+10]
        for row in selected:
            contact_path(row)
        values = [{'contact_id': row['contact_id'], 'lookup': row['lookup']} for row in selected]
        uri = AUTHORITY + '/export?' + urlencode({'items': json.dumps(values, separators=(',', ':'))})
        command = 'content read --uri ' + shlex.quote(uri)
        raw = adb_run(phone.adb, ['-s', phone.serial, 'exec-out', command], cancel, timeout=45)
        begins = len(re.findall(rb'(?im)^BEGIN:VCARD\s*$', raw))
        ends = len(re.findall(rb'(?im)^END:VCARD\s*$', raw))
        if begins != len(selected) or ends != len(selected):
            raise OSError('Contact export was incomplete. Click Enable contacts to update the phone companion, then retry. No completed backup was written.')
        report(min(1, (start+len(selected))/max(1,total)), f'Exported {start+len(selected)} of {total} contacts')
        yield raw


def delete_contacts(phone, rows, cancel, report):
    paths = [(row, contact_path(row)) for row in rows]  # validate whole selection first
    result = []
    for index, (row, path) in enumerate(paths):
        check_cancel(cancel)
        report(index / max(1, len(rows)), 'Deleting contact ' + row['name'])
        try:
            from .companion_link import Companion
            if isinstance(phone, Companion):
                success = bool(phone.call('delete_contact',cancel,contact_id=row['contact_id'],lookup=row['lookup']))
                result.append((row['id'],success,'Deleted' if success else 'Contact not deleted'))
                continue
            output = phone.shell('content delete --uri ' + shlex.quote(AUTHORITY + path), cancel).decode(errors='replace')
            match = re.search(r'Deleted (\d+) rows?', output)
            success = bool(match and int(match.group(1)) > 0)
            result.append((row['id'], success, 'Deleted' if success else 'Not deleted. Allow write access on the phone and reload contacts.'))
        except OSError as exc:
            result.append((row['id'], False, str(exc)))
    return result


def enable_contacts(phone, cancel, report):
    report(0, 'Installing Twist Contacts Bridge…')
    apk = resource_path('companion/TwistContactsBridge.apk')
    if not apk.is_file():
        raise OSError('Contacts companion is missing from this build.')
    output = adb_run(phone.adb, ['-s', phone.serial, 'install', '-r', str(apk)], cancel, timeout=180).decode(errors='replace')
    if 'Success' not in output:
        raise OSError('Android did not confirm companion installation: ' + output)
    phone.shell('am start -n com.twist.mediabridge.contacts/.MainActivity', cancel)
    return 'On your phone, tap Allow contacts access, approve the Contacts permission, then click Load contacts on this PC.'
