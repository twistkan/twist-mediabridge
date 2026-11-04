"""Read APK label metadata without downloading an app's code or assets."""
import io
import math
import re
import shlex
import tempfile
import zipfile
from pathlib import Path
from .engine import adb_run, check_cancel
from .desktop import resource_path


class RemoteZip(io.RawIOBase):
    def __init__(self, phone, path, cancel):
        self.phone, self.path, self.cancel = phone, path, cancel
        self.size = int(phone.shell('stat -c %s ' + shlex.quote(path), cancel).strip())
        self.position = 0
        self.blocks = {}

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset + (self.position if whence == 1 else self.size if whence == 2 else 0)
        if self.position < 0:
            raise ValueError('Invalid APK offset')
        return self.position

    def read(self, count=-1):
        check_cancel(self.cancel)
        count = min(self.size - self.position, count if count >= 0 else self.size)
        if count <= 0:
            return b''
        if count > 64 * 1024 * 1024:
            raise ValueError('APK metadata exceeds preview limit')
        start = self.position // 65536
        end = math.ceil((self.position + count) / 65536)
        if not all(i in self.blocks for i in range(start, end)):
            script = f'dd if={shlex.quote(self.path)} bs=65536 skip={start} count={end-start} 2>/dev/null'
            data = adb_run(self.phone.adb, ['-s', self.phone.serial, 'exec-out', script], self.cancel, timeout=30)
            for index in range(end-start):
                self.blocks[start+index] = data[index*65536:(index+1)*65536]
        chunk = b''.join(self.blocks[i] for i in range(start, end))
        offset = self.position % 65536
        self.position += count
        return chunk[offset:offset+count]


def app_label(phone, apk, cancel):
    with tempfile.TemporaryDirectory(prefix='twist-label-') as folder:
        metadata = Path(folder) / 'metadata.apk'
        with zipfile.ZipFile(RemoteZip(phone, apk, cancel)) as source, zipfile.ZipFile(metadata, 'w') as target:
            for name in ('AndroidManifest.xml', 'resources.arsc'):
                try:
                    entry = source.getinfo(name)
                except KeyError:
                    continue
                if entry.file_size > 64 * 1024 * 1024:
                    raise ValueError('APK metadata too large')
                target.writestr(name, source.read(entry))
        output = adb_run(resource_path('tools/aapt2/aapt2.exe'), ['dump', 'badging', str(metadata)], cancel, timeout=15).decode('utf-8', errors='replace')
        labels = re.findall(r"^application-label(?:-en)? :'([^']*)'", output, re.MULTILINE)
        if not labels:
            labels = re.findall(r"^application-label(?:-en)?:'([^']*)'", output, re.MULTILINE)
        if not labels:
            raise ValueError('App label unavailable')
        return labels[0]
