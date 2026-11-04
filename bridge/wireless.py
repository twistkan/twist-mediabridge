"""Explicit Android 11+ wireless-debugging pairing; no internet services."""
import ipaddress
import re
import socket
from .engine import adb_run, discover, Cancelled, check_cancel


class PairingRequired(OSError):
    """The selected phone needs pairing guidance before access is available."""


def endpoint(value):
    value = value.strip()
    match = re.fullmatch(r'(\[[0-9a-fA-F:]+\]|[0-9.]+):([0-9]{1,5})', value)
    if not match:
        raise ValueError('Enter the phone IP address and port, for example 192.168.1.20:37123.')
    host, port = match.groups()
    try:
        address = ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        raise ValueError('The phone IP address is invalid.') from None
    if address.is_multicast or address.is_unspecified or address.is_loopback or not 1 <= int(port) <= 65535:
        raise ValueError('Enter a phone address on your local network and a port from 1 to 65535.')
    return f'[{address}]:{int(port)}' if address.version == 6 else f'{address}:{int(port)}'


def wireless_serial(serial):
    try:
        endpoint(serial)
        return True
    except ValueError:
        return bool(re.fullmatch(r'[A-Za-z0-9_.-]+\._adb-tls-connect\._tcp\.?', serial))


def pair(adb, address, code, cancel):
    address = endpoint(address)
    if not re.fullmatch(r'[0-9]{6}', code):
        raise ValueError('Enter the six-digit pairing code currently shown on the phone.')
    try:
        # Keep the short-lived code out of process arguments and saved settings.
        output = adb_run(adb, ['pair', address], cancel, timeout=45,
                         input_data=(code + '\n').encode('ascii')).decode('utf-8', errors='replace')
    except (OSError, TimeoutError):
        raise OSError('Pairing failed. Keep the pairing-code popup open, check its address/port and use its current code. Both devices must be on the same Wi-Fi.') from None
    if 'successfully paired to ' not in output.lower():
        raise OSError('Phone did not confirm pairing. Generate a fresh code and check the pairing port.')
    return 'Paired. Close the phone pairing popup; use IP address & Port on the main Wireless debugging screen for Step 2.'


def connect(adb, address, cancel, service=''):
    address = endpoint(address)
    try:
        try:
            output = adb_run(adb, ['connect', address], cancel, timeout=12).decode('utf-8', errors='replace').lower()
        except OSError as exc:
            if any(word in str(exc).lower() for word in ('authenticate', 'authentication', 'unauthorized')):
                raise PairingRequired('Phone detected, but this computer is not paired. Open Pair device with pairing code on the phone.') from None
            raise
        if any(word in output for word in ('authenticate', 'authentication', 'unauthorized')):
            raise PairingRequired('Phone detected, but this computer is not paired. Open Pair device with pairing code on the phone.')
        if not any(line.strip().startswith(('connected to ', 'already connected to ')) for line in output.splitlines()):
            raise OSError('not connected')
        try:
            state = adb_run(adb, ['-s', address, 'get-state'], cancel, timeout=5).strip()
        except OSError as exc:
            if 'unauthorized' in str(exc).lower():
                raise PairingRequired('The phone has not authorized this computer. Pair it using the code shown on the phone.') from None
            state = b''  # ADB may already know it by its mDNS service serial.
        if state == b'unauthorized':
            raise PairingRequired('The phone has not authorized this computer. Pair it using the code shown on the phone.')
        ready, blocked = discover(adb)
        matched = [phone for phone in ready if phone.serial == address or
                   (service and phone.serial.rstrip('.') == service.rstrip('.') + '._adb-tls-connect._tcp')]
        if not matched:
            if 'unauthorized' in blocked:
                raise PairingRequired('The phone has not authorized this computer. Pair it using its current code.')
            raise OSError('Selected phone was not found as an authorized connection')
        if not (state == b'device' and matched[0].serial == address):
            if adb_run(adb, ['-s', matched[0].serial, 'get-state'], cancel, timeout=5).strip() != b'device':
                raise OSError('Selected phone is not online')
    except PairingRequired:
        raise
    except (OSError, TimeoutError):
        raise OSError('Could not connect. The phone may have gone offline or changed its connection port. Keep Wireless debugging enabled, find the phone again and retry. Check the local Wi-Fi and router/firewall settings.') from None
    return ready, blocked


def disconnect(adb, serial, cancel):
    if not wireless_serial(serial):
        raise ValueError('Select a Wi-Fi connection; USB devices are left connected.')
    output = adb_run(adb, ['disconnect', serial], cancel, timeout=15).decode('utf-8', errors='replace').lower()
    if 'disconnected ' not in output:
        raise OSError('Could not disconnect that Wi-Fi device. Turn off Wireless debugging on the phone.')
    return serial


def parse_services(output, include_qr=False):
    """Only accept resolved TLS debugging advertisements, never legacy TCP."""
    rows, seen = [], set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        name, kind, address = fields
        kind = kind.rstrip('.')
        if kind not in ('_adb-tls-pairing._tcp', '_adb-tls-connect._tcp'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,255}', name) or (name.startswith('studio-') and not include_qr):
            continue  # QR pairing servers cannot accept a six-digit PIN.
        try:
            address = endpoint(address)
        except ValueError:
            continue
        key = (name, kind, address)
        if key in seen:
            continue
        seen.add(key)
        rows.append({'name': name, 'kind': kind, 'address': address,
                     'host': address.rsplit(':', 1)[0]})
    return rows


def service_snapshot(adb, cancel, direct_fallback=True):
    check_cancel(cancel)
    try:
        output = adb_run(adb, ['mdns', 'services'], cancel, timeout=8)
    except (OSError, TimeoutError):
        raise OSError('Nearby discovery is unavailable. Check private-network firewall access, or open Advanced manual connection.') from None
    rows = parse_services(output.decode('utf-8', errors='replace'))
    if not rows and direct_fallback:
        rows = [row for row in multicast_snapshot(cancel) if not row['name'].startswith('studio-')]
    return rows


def multicast_snapshot(cancel, seconds=3):
    from .network_discovery import scan
    try:
        return scan(cancel, seconds)
    except (OSError, RuntimeError):
        return []


def merge_services(*groups):
    merged = {}
    for group in groups:
        for row in group:
            # Prefer a newly queried port over an older ADB-cache port.
            merged[(row['name'], row['kind'], row['host'])] = row
    return list(merged.values())


def candidates(services, ready):
    """Pair/connect advertisements share a host, but don't guess ambiguous links."""
    rows = []
    for host in sorted({row['host'] for row in services}):
        pairs = [row for row in services if row['host'] == host and row['kind'] == '_adb-tls-pairing._tcp']
        connections = [row for row in services if row['host'] == host and row['kind'] == '_adb-tls-connect._tcp']
        for item in pairs or connections:
            connection = connections[0] if len(connections) == 1 and len(pairs) <= 1 else (item if not pairs else None)
            row = {'id': item['name'] + '|' + item['address'], 'name': item['name'], 'host': host,
                   'pair_address': item['address'] if pairs else '',
                   'connect_address': connection['address'] if connection else '',
                   'connect_service': connection['name'] if connection else '', 'connected_serial': '',
                   'label': 'Android phone · ' + item['name']}
            for phone in ready:
                if phone.serial == row['connect_address'] or (row['connect_service'] and phone.serial.rstrip('.') == row['connect_service'].rstrip('.') + '._adb-tls-connect._tcp'):
                    row['connected_serial'], row['label'] = phone.serial, phone.label
            rows.append(row)
    for phone in ready:
        if wireless_serial(phone.serial) and not any(row['connected_serial'] == phone.serial for row in rows):
            try:
                address = endpoint(phone.serial)
            except ValueError:
                address = ''
            rows.append({'id': phone.serial, 'name': phone.serial, 'host': address.rsplit(':', 1)[0] if address else '',
                         'pair_address': '', 'connect_address': address, 'connect_service': '',
                         'connected_serial': phone.serial, 'label': phone.label})
    return rows


def nearby(adb, cancel, wait_seconds=5):
    check_cancel(cancel)
    try:
        cached = service_snapshot(adb, cancel, direct_fallback=False)
    except (OSError, TimeoutError):
        cached = []
    direct = multicast_snapshot(cancel, seconds=max(1, wait_seconds))
    services = merge_services(cached, [row for row in direct if not row['name'].startswith('studio-')])
    check_cancel(cancel)
    ready, _ = discover(adb)
    check_cancel(cancel)
    return candidates(services, ready)


def connect_candidate(adb, row, cancel):
    serial = row.get('connected_serial')
    if serial and wireless_serial(serial):
        try:
            if adb_run(adb, ['-s', serial, 'get-state'], cancel, timeout=5).strip() == b'device':
                result = discover(adb)
                if any(phone.serial == serial for phone in result[0]):
                    return result, serial
        except (OSError, TimeoutError):
            pass
    if not row.get('connect_address'):
        raise PairingRequired('The phone is ready to pair. Enter its current six-digit code and choose Pair & connect.')
    address, service = row['connect_address'], row.get('connect_service', '')
    try:
        fresh = [item for item in service_snapshot(adb, cancel)
                 if item['kind'] == '_adb-tls-connect._tcp' and item['host'] == row['host']]
        exact = [item for item in fresh if item['name'] == service]
        if len(exact) == 1 or len(fresh) == 1:
            item = exact[0] if len(exact) == 1 else fresh[0]
            address, service = item['address'], item['name']
    except (OSError, TimeoutError):
        pass
    try:
        result = connect(adb, address, cancel, service=service)
    except PairingRequired:
        raise
    except (OSError, TimeoutError):
        if service and not serial and port_reachable(address, cancel):
            raise PairingRequired('The phone is reachable, but Android did not complete an authorized connection. '
                                  'Pair this computer using the code shown on the phone. If already paired, '
                                  'check the phone settings or Forget this computer and pair again.') from None
        raise
    target = next((phone.serial for phone in result[0] if phone.serial == address or
                   (service and phone.serial.rstrip('.') == service.rstrip('.') + '._adb-tls-connect._tcp')), '')
    if not target:
        raise OSError('The selected phone is not online. Find nearby phones again.')
    return result, target


def port_reachable(address, cancel):
    check_cancel(cancel)
    host, port = endpoint(address).rsplit(':', 1)
    try:
        with socket.create_connection((host.strip('[]'), int(port)), timeout=2):
            return True
    except OSError:
        return False
    finally:
        check_cancel(cancel)


def wait_for_pin_server(adb, row, cancel, timeout_seconds=60, report=None):
    """Wait for the selected phone's explicit code popup, never invent a PIN."""
    import time
    if not row.get('host'):
        raise ValueError('Find nearby phones again so the selected phone can be identified before code pairing.')
    deadline = time.monotonic() + timeout_seconds
    if report:
        report('On the PHONE: open Wireless debugging → Pair device with pairing code. No notification is sent. Waiting for that screen…')
    while True:
        check_cancel(cancel)
        matches = [item for item in service_snapshot(adb, cancel)
                   if item['host'] == row['host'] and item['kind'] == '_adb-tls-pairing._tcp'
                   and not item['name'].startswith('studio-')]
        if len(matches) == 1:
            return dict(row, pair_address=matches[0]['address'])
        if len(matches) > 1:
            raise OSError('More than one code-pairing service was advertised for this phone. Close old pairing screens and open a fresh code screen.')
        if time.monotonic() >= deadline:
            raise TimeoutError('The phone code screen was not detected. Open Wireless debugging → Pair device with pairing code on the PHONE, then try Pair using code again. Connecting on the PC does not send a notification or generate a code.')
        if cancel is not None:
            cancel.wait(.5)
        else:
            time.sleep(.5)


def pair_and_connect(adb, row, code, cancel, report=None):
    if not row.get('pair_address'):
        matches = [item for item in service_snapshot(adb, cancel)
                   if item['host'] == row['host'] and item['kind'] == '_adb-tls-pairing._tcp']
        if len(matches) != 1:
            raise ValueError('On the selected phone open Pair device with pairing code. Enter that code here and click Pair & connect again.')
        row = dict(row, pair_address=matches[0]['address'])
    pair(adb, row['pair_address'], code, cancel)
    return finish_pairing(adb, row, cancel, report)


def finish_pairing(adb, row, cancel, report=None):
    if report:
        report('Paired. Finding and connecting this phone automatically…')
    # ADB may auto-connect after pairing. Otherwise resolve the current TLS port.
    # Never use another host or an arbitrary phone already on this computer.
    import time
    deadline = time.monotonic() + 8
    while True:
        check_cancel(cancel)
        try:
            services = service_snapshot(adb, cancel)
        except (OSError, TimeoutError):
            break
        matches = {item['address'] for item in services
                   if item['host'] == row['host'] and item['kind'] == '_adb-tls-connect._tcp'}
        if len(matches) == 1:
            address = matches.pop()
            try:
                # ADB can auto-connect using a service-name serial after pairing.
                # Accept only the selected host's uniquely resolved TLS service.
                names = {item['name'].rstrip('.') + '._adb-tls-connect._tcp'
                         for item in services if item['address'] == address and item['kind'] == '_adb-tls-connect._tcp'}
                ready, blocked = discover(adb)
                for phone in ready:
                    if phone.serial == address or phone.serial.rstrip('.') in names:
                        if adb_run(adb, ['-s', phone.serial, 'get-state'], cancel, timeout=5).strip() == b'device':
                            return (ready, blocked), phone.serial
                return connect(adb, address, cancel), address
            except (OSError, TimeoutError):
                break
        if len(matches) > 1 or time.monotonic() >= deadline:
            break
        if cancel is not None:
            cancel.wait(.5)
        else:
            time.sleep(.5)
    raise OSError('Pairing succeeded, but automatic connection is not ready. Close the phone pairing popup, click Find nearby phones again and Connect selected. Advanced manual connection is available if discovery is blocked.')
