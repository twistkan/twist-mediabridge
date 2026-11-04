"""Direct local mDNS queries independent of the shared ADB server's cache."""
import queue
import time
from .engine import check_cancel

TLS_TYPES = ('_adb-tls-pairing._tcp.local.', '_adb-tls-connect._tcp.local.')


def scan(cancel, seconds=3):
    from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, IPVersion, InterfaceChoice
    from .wireless import parse_services
    changes = queue.Queue()
    rows = {}
    def changed(zeroconf, service_type, name, state_change):
        changes.put((service_type, name, state_change))
    browser = None
    check_cancel(cancel)
    with Zeroconf(interfaces=InterfaceChoice.All, ip_version=IPVersion.V4Only) as zc:
        try:
            browser = ServiceBrowser(zc, list(TLS_TYPES), handlers=[changed])
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                check_cancel(cancel)
                try:
                    kind, name, state = changes.get(timeout=.15)
                except queue.Empty:
                    continue
                key = (kind, name)
                if state == ServiceStateChange.Removed:
                    rows.pop(key, None)
                    continue
                info = zc.get_service_info(kind, name, timeout=500)
                if info is None:
                    continue
                suffix = '.' + kind
                if not name.endswith(suffix):
                    continue
                instance = name[:-len(suffix)]
                service = kind.removesuffix('.local.')
                parsed = []
                for address in info.parsed_addresses(IPVersion.V4Only):
                    parsed.extend(parse_services(f'{instance} {service} {address}:{info.port}', include_qr=True))
                rows[key] = parsed
        finally:
            if browser is not None:
                browser.cancel()
    check_cancel(cancel)
    return [row for group in rows.values() for row in group]
