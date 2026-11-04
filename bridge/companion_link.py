"""Ephemeral, certificate-pinned local companion sessions. No ADB commands."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import secrets
import ssl
import tempfile
import threading
import time
from urllib.parse import urlencode

from .engine import Android, category, check_cancel, digest, safe_relative

CHUNK = 512 * 1024
MAX_BODY = 32 * 1024 * 1024


def windows_media_path(name):
    """Give Android-only names stable Windows aliases; never change the phone."""
    if not isinstance(name,str) or not name or name.startswith('/') or any(p in ('','.','..') for p in name.split('/')):
        raise ValueError('Unsafe companion file path')
    parts=[]
    for original in name.split('/'):
        try:
            safe_relative(original)
            if len(original)>180:raise ValueError('Long file name')
            part=original
        except ValueError:
            clean=re.sub(r'[<>:"\\|?*\x00-\x1f]','_',original).rstrip(' .') or 'Unnamed'
            suffix=Path(clean).suffix[:20]
            stem=clean[:-len(suffix)] if suffix else clean
            part=stem[:140]+'~'+hashlib.sha256(original.encode('utf-8')).hexdigest()[:12]+suffix
            safe_relative(part)
        parts.append(part)
    result='/'.join(parts)
    safe_relative(result)
    return result


def local_addresses():
    import ifaddr
    found = []
    for adapter in ifaddr.get_adapters():
        for item in adapter.ips:
            if isinstance(item.ip, str):
                address = ipaddress.ip_address(item.ip)
                if address.version == 4 and not address.is_loopback and not address.is_link_local:
                    found.append(str(address))
    return sorted(set(found))


def certificate(folder):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Twist local session')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    cert_file, key_file = Path(folder) / 'cert.pem', Path(folder) / 'key.pem'
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_file, key_file, cert.fingerprint(hashes.SHA256()).hex()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self,*args):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args)

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class Link:
    def __init__(self, address):
        ipaddress.IPv4Address(address)
        self.temp = tempfile.TemporaryDirectory(prefix='twist-link-')
        self.lock = threading.RLock()
        self.pending = {}
        self.wakeup = threading.Event()
        self.stopped = False
        self.enrollment = secrets.token_hex(32)
        self.deadline = time.monotonic() + 300
        self.token = None
        self.peer = None
        self.model = ''
        self.last_seen = 0
        self.joined = False
        try:
            cert, key, self.fingerprint = certificate(self.temp.name)
            self.server = LocalServer((address, 0), Handler)
            self.server.daemon_threads = True
            self.server.link = self
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(cert), str(key))
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True,do_handshake_on_connect=False)
            self.address = address
            self.port = self.server.server_port
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        except Exception:
            self.temp.cleanup()
            raise

    def uri(self):
        return 'twistbridge://connect?' + urlencode(dict(host=self.address, port=self.port,
                    fingerprint=self.fingerprint, token=self.enrollment))

    def online(self):
        with self.lock:
            return bool(self.joined and not self.stopped and time.monotonic() - self.last_seen < 15)

    def disconnect_reason(self):
        if self.stopped or not self.token:return 'The companion session was closed.'
        with self.lock:
            phase=next((item[2]['operation'] for item in self.pending.values()),'idle')
        label={'info':'file verification','read':'file transfer','thumbnail':'thumbnail loading','files':'album scanning'}.get(phase,'the session')
        return f'No authenticated phone traffic received for 15 seconds during {label}.'

    def request(self, operation, cancel=None, **arguments):
        check_cancel(cancel)
        if not self.online():
            raise OSError('Companion disconnected. Open the phone companion and pair again.')
        key = secrets.token_hex(16)
        item = dict(id=key, operation=operation, arguments=arguments)
        event = threading.Event()
        with self.lock:
            if len(self.pending)>=32:
                raise OSError('Phone request queue is busy. Please retry.')
            self.pending[key] = [event, None, item, 0.0]
            self.wakeup.set()
        try:
            start = time.monotonic()
            while not event.wait(.1):
                check_cancel(cancel)
                if not self.online() or time.monotonic() - start > 180:
                    raise OSError('Phone did not complete the request. Keep its companion open and retry.')
            result = self.pending[key][1]
            check_cancel(cancel)
            if not result or 'error' in result:
                raise OSError((result or {}).get('error', 'Companion connection closed.'))
            return result['value']
        finally:
            with self.lock:
                self.pending.pop(key, None)

    def close(self):
        with self.lock:
            if self.stopped:
                return
            self.stopped = True
            self.token = None
            self.enrollment = ''
            for item in self.pending.values():
                item[0].set()
            self.wakeup.set()
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def next_job(self):
        """Redeliver an unacknowledged poll after packet loss, using the same ID."""
        with self.lock:
            now=time.monotonic()
            for event, result, job, delivered in self.pending.values():
                if not event.is_set() and (not delivered or now-delivered>=5):
                    self.pending[job['id']][3]=now
                    return job
            self.wakeup.clear()
            return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)
        self.connection.do_handshake()

    def log_message(self, *args):
        pass  # Never log pairing tokens, contacts or media paths.

    def reply(self, code, data):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        link = self.server.link
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 0 or size > MAX_BODY:
                self.reply(413, {'error': 'Request too large'})
                return
            supplied = self.headers.get('Authorization', '')
            with link.lock:
                joining = self.path == '/join'
                expected = link.enrollment if joining else link.token
                allowed = (not link.stopped and expected and
                           hmac.compare_digest(supplied, 'Bearer ' + expected))
                if joining:
                    allowed = allowed and not link.joined and time.monotonic() < link.deadline
                else:
                    allowed = allowed and link.online() and link.peer == self.client_address[0]
                if not allowed:
                    self.reply(403, {'error': 'Session unavailable. Pair again.'})
                    return
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError('Incomplete request')
            data = json.loads(raw)
            with link.lock:
                if joining:
                    # Recheck under the lock so two phones cannot enroll concurrently.
                    if link.joined or time.monotonic() >= link.deadline:
                        self.reply(403, {'error': 'Pairing expired'})
                        return
                    model = data.get('model')
                    if not isinstance(model, str) or not model.strip() or len(model) > 120 or not model.isprintable():
                        raise ValueError('Invalid phone identity')
                    link.model = model
                    link.token = secrets.token_hex(32)
                    link.peer = self.client_address[0]
                    link.last_seen = time.monotonic()
                    link.joined = True
                    link.enrollment = ''
                    self.reply(200, {'token': link.token})
                    return
                link.last_seen = time.monotonic()
            if self.path == '/heartbeat':
                self.reply(200, {'ok': True})
            elif self.path == '/poll':
                item=link.next_job()
                if item is None:
                    link.wakeup.wait(1)
                    item=link.next_job()
                self.reply(200, {'job': item})
            elif self.path == '/result':
                with link.lock:
                    item = link.pending.get(data.get('id'))
                    if not item or not isinstance(data.get('result'), dict):
                        self.reply(409, {'error': 'Request no longer active'})
                        return
                    if not item[0].is_set():
                        item[1] = data['result']
                        item[0].set()
                self.reply(200, {'ok': True})
            elif self.path == '/disconnect':
                with link.lock:
                    link.last_seen = 0
                    link.token = None
                self.reply(200, {'ok': True})
            else:
                self.reply(404, {'error': 'Unknown operation'})
        except (ValueError, KeyError, TypeError):
            self.reply(400, {'error': 'Invalid request'})
        except (OSError, ssl.SSLError):
            pass


class Companion(Android):
    """An endpoint implementing existing transfer interfaces without an ADB shell."""
    kind = 'companion'

    def __init__(self, link):
        self.link = link
        self.key = 'companion:' + secrets.token_hex(12)
        self.label = link.model + ' · Companion Wi-Fi'
        self.scan_warnings = []
        self.metadata = {}

    def online(self, cancel=None):
        check_cancel(cancel)
        return self.link.online()

    def call(self, operation, cancel=None, **args):
        return self.link.request(operation, cancel, **args)

    def shell(self, *args):
        raise OSError('This action requires USB or Android wireless debugging. Those connection methods remain available.')

    def remote(self, name):
        safe_relative(name)
        return self.metadata.get(name,{}).get('remote_path',name)

    def files(self, selected, cancel):
        rows = self.call('files', cancel)
        metadata = {}
        renamed=0
        self.scan_warnings=[]
        for row in rows:
            check_cancel(cancel)
            original=row['path']
            name=windows_media_path(original)
            renamed+=name!=original
            size = int(row['size'])
            if size < 0 or name in metadata:
                raise ValueError('Invalid companion file listing')
            metadata[name] = dict(row,remote_path=original)
        self.metadata = metadata
        if renamed:
            self.scan_warnings=[f'{renamed} file paths adapted for Windows. Original phone names are unchanged.']
        for name, row in metadata.items():
            if category(name) in selected:
                yield name, row['size']

    def media_files(self, cancel, report):
        report(0, 'Reading folders approved in your phone companion…')
        yield from self.files({'Photos', 'Videos'}, cancel)

    def stamp(self, name, cancel):
        if not self.online(cancel):
            raise OSError('Phone disconnected')
        row = self.metadata[name]
        return f"{row['size']}:{row['modified']}"

    def read(self, name, temp, cancel):
        remote=self.remote(name)
        info = self.call('info', cancel, path=remote)
        size = int(info['size'])
        expected = info['sha256']
        if size < 0 or len(expected) != 64:
            raise ValueError('Invalid phone file metadata')
        target = Path(temp) / secrets.token_hex(12)
        try:
            with target.open('xb') as out:
                for offset in range(0, size, CHUNK):
                    check_cancel(cancel)
                    raw = self.call('read', cancel, path=remote, offset=offset, size=min(CHUNK, size-offset))
                    chunk = base64.b64decode(raw, validate=True)
                    if len(chunk) != min(CHUNK, size-offset):
                        raise OSError('Incomplete phone file')
                    out.write(chunk)
            if digest(target, cancel) != expected:
                raise OSError('Phone file changed or failed checksum verification')
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def install_apks(self, paths, cancel, report):
        """Stage verified APKs; Android's phone UI owns approval and final result."""
        identities = []
        request = None
        try:
            paths = list(paths)
            if not paths or len(paths) > 500:
                raise ValueError('Select between 1 and 500 APK parts.')
            for index, path in enumerate(paths):
                source = Path(path)
                if source.suffix.lower() != '.apk' or not source.is_file():
                    raise ValueError('Select APK installation files only.')
                check_cancel(cancel)
                report(index / len(paths), 'Sending APK to phone: ' + source.name)
                try:
                    identity = self.call('install_upload_begin', cancel, path=f'part-{index}.apk',
                                         size=source.stat().st_size, sha256=digest(source, cancel))
                except OSError as error:
                    if 'needs USB or Android wireless debugging' in str(error):
                        raise OSError('Update Twist Companion on the phone to version 1.5, then reconnect and retry installation.') from error
                    raise
                identities.append(identity)
                with source.open('rb') as inp:
                    offset = 0
                    while chunk := inp.read(CHUNK):
                        self.call('upload_chunk', cancel, id=identity, offset=offset,
                                  data=base64.b64encode(chunk).decode())
                        offset += len(chunk)
            request = self.call('install_prepare', cancel, ids=identities)
            report(0.95, 'On the phone: open Twist Companion and approve installation. If asked, allow installs from this source.')
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                check_cancel(cancel)
                result = self.call('install_status', cancel, id=request)
                if result['status'] == 'installed':
                    return 'Android confirmed app installation.'
                if result['status'] == 'failed':
                    raise OSError(result.get('message') or 'Android refused installation.')
                if cancel is not None:
                    cancel.wait(0.5)
                else:
                    time.sleep(0.5)
            raise OSError('Installation approval timed out. Check the phone before trying again.')
        finally:
            if self.online():
                if request:
                    try: self.call('install_release', id=request)
                    except OSError: pass
                for identity in identities:
                    try: self.call('upload_abort', id=identity)
                    except OSError: pass

    def write(self, source, name, cancel):
        self.remote(name)
        source = Path(source)
        expected = digest(source, cancel)
        identity = self.call('upload_begin', cancel, path=name, size=source.stat().st_size, sha256=expected)
        try:
            with source.open('rb') as inp:
                offset = 0
                while chunk := inp.read(CHUNK):
                    self.call('upload_chunk', cancel, id=identity, offset=offset,
                              data=base64.b64encode(chunk).decode())
                    offset += len(chunk)
            status = self.call('upload_finish', cancel, id=identity)
            if status not in ('copied', 'already present'):
                raise OSError('Phone did not confirm completed transfer')
            return expected, status
        finally:
            if self.online():
                try:
                    self.call('upload_abort', id=identity)
                except OSError:
                    pass


def phone_online(phone, cancel=None, runner=None):
    if isinstance(phone, Companion):
        return phone.online(cancel)
    from .engine import adb_run
    return (runner or adb_run)(phone.adb, ['-s', phone.serial, 'get-state'], cancel, timeout=2).strip() == b'device'


def retain_companions(endpoints, phones):
    return [e for e in endpoints if (not isinstance(e, Android) or isinstance(e, Companion) and e.online())] + phones
