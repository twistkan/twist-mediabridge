"""Android's documented ADB QR protocol, with ephemeral local sessions."""
from dataclasses import dataclass, field
import re
import secrets
import time
from .engine import adb_run, check_cancel
from . import wireless


@dataclass(frozen=True)
class Session:
    name: str
    secret: str = field(repr=False)
    expires: float

    @property
    def payload(self):
        return f'WIFI:T:ADB;S:{self.name};P:{self.secret};;'


def new_session(lifetime=300):
    return Session('studio-twist-' + secrets.token_hex(6), secrets.token_hex(12), time.monotonic() + lifetime)


def image(session):
    import qrcode
    from qrcode.image.pil import PilImage
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
    qr.add_data(session.payload)
    qr.make(fit=True)
    return qr.make_image(image_factory=PilImage).get_image().convert('RGB')


def snapshot(adb, cancel):
    try:
        output = adb_run(adb, ['mdns', 'services'], cancel, timeout=8)
        cached = wireless.parse_services(output.decode('utf-8', errors='replace'), include_qr=True)
    except (OSError, TimeoutError):
        cached = []
    return wireless.merge_services(cached, wireless.multicast_snapshot(cancel, seconds=2))


def pair_session(adb, session, cancel, report=None):
    if not re.fullmatch(r'studio-twist-[0-9a-f]{12}', session.name) or not re.fullmatch(r'[0-9a-f]{24}', session.secret):
        raise ValueError('Invalid QR pairing session. Generate a new QR code.')
    while time.monotonic() < session.expires:
        check_cancel(cancel)
        matches = [row for row in snapshot(adb, cancel)
                   if row['kind'] == '_adb-tls-pairing._tcp' and row['name'] == session.name]
        if time.monotonic() >= session.expires:
            break
        if matches:
            if len(matches) != 1:
                raise OSError('More than one phone scanned this code. Close it and generate a new QR code.')
            row = matches[0]
            if report:
                report('Phone scanned the code. Pairing securely…')
            try:
                output = adb_run(adb, ['pair', wireless.endpoint(row['address'])], cancel, timeout=45,
                                 input_data=(session.secret + '\n').encode('ascii')).decode('utf-8', errors='replace')
            except (OSError, TimeoutError):
                raise OSError('QR pairing failed. Generate a new code and scan it from the phone Wireless debugging QR scanner.') from None
            if 'successfully paired to ' not in output.lower():
                raise OSError('Phone did not confirm QR pairing. Generate a new code and scan again.')
            return wireless.finish_pairing(adb, row, cancel, report)
        if cancel is not None:
            cancel.wait(.5)
        else:
            time.sleep(.5)
    check_cancel(cancel)
    raise TimeoutError('QR code expired. Close it and choose Pair with QR code again. Keep both devices on the same local network and use the phone Wireless debugging QR scanner.')
