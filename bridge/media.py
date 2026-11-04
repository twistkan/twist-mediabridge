"""Folder-backed albums and local-only preview caching."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tempfile
import threading

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import imageio_ffmpeg

from .engine import Folder, category, contained, check_cancel, adb_run

# Use the packaged executable directly, avoiding subprocess-based discovery.
from .desktop import resource_path
_bundled_ffmpeg = resource_path('imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe')
if _bundled_ffmpeg.is_file():
    os.environ['IMAGEIO_FFMPEG_EXE'] = str(_bundled_ffmpeg)
register_heif_opener()
MEDIA_TYPES = {'Photos', 'Videos'}
PAGE_SIZE = 12


def scan_media(source, cancel, report, on_batch=None):
    report(0, 'Reading media folders…')
    items = []
    import time
    last_batch = time.monotonic()
    files = source.media_files(cancel, report) if hasattr(source, 'media_files') else source.files(MEDIA_TYPES, cancel)
    for name, size in files:
        check_cancel(cancel)
        parent = str(PurePosixPath(name).parent)
        items.append({'path': name, 'album': parent if parent != '.' else 'Main folder',
                      'kind': category(name), 'size': size})
        if on_batch and len(items) % 128 == 0 and (time.monotonic() - last_batch >= .2):
            on_batch(list(items))
            last_batch = time.monotonic()
    items.sort(key=lambda item: item['path'].casefold())
    report(1, f'{len(items):,} photos and videos found')
    return items


def album_counts(items):
    albums = {}
    for item in items:
        albums[item['album']] = albums.get(item['album'], 0) + 1
    return dict(sorted(albums.items(), key=lambda pair: pair[0].casefold()))


class MediaCache:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.thumbnails = self.root / 'thumbnails'
        self.thumbnails.mkdir(exist_ok=True)
        self.locks = {}
        self.lock_guard = threading.Lock()

    def local(self, source, name, cancel, thumbnail=False):
        check_cancel(cancel)
        if isinstance(source, Folder):
            return contained(source.root, name)
        remote = source.remote(name)
        stamp = source.stamp(name, cancel) if hasattr(source, 'stamp') else source.shell('stat -c %s:%Y ' + shlex.quote(remote), cancel).decode().strip()
        size = int(stamp.split(':')[0])
        if thumbnail and size > 80 * 1024 * 1024:
            raise ValueError('Large media · click to load preview')
        key = hashlib.sha256((source.key + '\0' + name + '\0' + stamp).encode()).hexdigest()
        cached = self.root / (key + PurePosixPath(name).suffix.lower())
        if cached.is_file():
            if cached.stat().st_size == size:
                os.utime(cached, None)
                return cached
            cached.unlink()
        with tempfile.TemporaryDirectory(prefix='preview-') as temp:
            fetched = source.read(name, temp, cancel)
            stage = self.root / (key + '.partial')
            try:
                import shutil
                shutil.copyfile(fetched, stage)
                check_cancel(cancel)
                os.replace(stage, cached)
            finally:
                stage.unlink(missing_ok=True)
        self.trim(cached)
        return cached

    def trim(self, keep):
        # Keep recently used originals; previews are local, never uploaded.
        files = sorted((p for p in self.root.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime)
        size = sum(p.stat().st_size for p in files)
        for file in files:
            if size <= 1024 * 1024 * 1024:
                break
            if file != keep:
                try:
                    size -= file.stat().st_size
                    file.unlink()
                except OSError:
                    pass

    def image(self, source, name, cancel, size=(150, 108), thumbnail=True, pad=True):
        with self.lock_guard:
            lock = self.locks.setdefault((source.key, name), threading.Lock())
        with lock:
            return self._image(source, name, cancel, size, thumbnail, pad)

    def _image(self, source, name, cancel, size, thumbnail, pad=True):
        from .companion_link import Companion
        if thumbnail and isinstance(source,Companion):
            import base64
            import io
            stamp=source.stamp(name,cancel)
            key=hashlib.sha256(f'{source.key}|{name}|{stamp}|{size}|companion-v1'.encode()).hexdigest()
            poster=self.thumbnails/(key+'.png')
            if poster.is_file():
                with Image.open(poster) as cached:return cached.copy(),poster
            raw=base64.b64decode(source.call('thumbnail',cancel,path=source.remote(name)),validate=True)
            if len(raw)>2*1024*1024:raise ValueError('Phone thumbnail too large')
            with Image.open(io.BytesIO(raw)) as picture:
                image=ImageOps.fit(picture.convert('RGB'),size,method=Image.Resampling.LANCZOS)
            check_cancel(cancel)
            image.save(poster,format='PNG')
            return image,poster
        local = self.local(source, name, cancel, thumbnail=thumbnail)
        stat = local.stat()
        key = hashlib.sha256(f'{local}|{stat.st_size}|{stat.st_mtime_ns if isinstance(source, Folder) else 0}|{size}|v1'.encode()).hexdigest()
        poster = self.thumbnails / (key + '.png')
        if thumbnail and poster.is_file():
            try:
                with Image.open(poster) as cached:
                    return cached.copy(), local
            except OSError:
                poster.unlink(missing_ok=True)
        if category(name) == 'Videos':
            fd, output = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            try:
                args = ['-nostdin', '-v', 'error', '-y', '-i', str(local), '-frames:v', '1',
                        '-vf', f'scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease', output]
                adb_run(imageio_ffmpeg.get_ffmpeg_exe(), args, cancel, timeout=120)
                with Image.open(output) as picture:
                    image = picture.convert('RGB')
            finally:
                Path(output).unlink(missing_ok=True)
        else:
            with Image.open(local) as picture:
                picture.draft('RGB', size)
                image = ImageOps.exif_transpose(picture).convert('RGB')
                image.thumbnail(size, Image.Resampling.LANCZOS)
        if thumbnail:
            image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        elif pad:
            image = ImageOps.pad(image, size, color=(16, 21, 31))
        if thumbnail:
            image.save(poster, format='PNG')
        return image, local


def video_duration(local):
    reader = imageio_ffmpeg.read_frames(str(local))
    try:
        return max(0., float(next(reader).get('duration') or 0))
    finally:
        reader.close()


def play_frames(local, cancel, emit, start=0., position=None, single=False):
    """Muted embedded playback; audio/fullscreen uses the system player."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    start = max(0., float(start))
    args = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error']
    if not single: args += ['-re']
    args += ['-ss', str(start), '-i', str(local), '-an',
            '-vf', 'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2',
            '-r', '12']
    if single: args += ['-frames:v', '1']
    args += ['-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1']
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, creationflags=flags)
        def terminate():
            while process.poll() is None:
                if cancel.wait(.1):
                    process.kill()
                    return
        threading.Thread(target=terminate, daemon=True).start()
        try:
            count = 640 * 360 * 3
            frame_number = 0
            while not cancel.is_set():
                frame = process.stdout.read(count)
                if len(frame) != count:
                    break
                if position: position(start + frame_number / 12)
                emit(Image.frombytes('RGB', (640, 360), frame))
                frame_number += 1
            process.wait()
            if process.returncode and not cancel.is_set():
                raise ValueError('This video could not be played. Try the system player.')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
