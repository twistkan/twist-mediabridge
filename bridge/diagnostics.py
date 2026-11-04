"""Packaged-runtime smoke test, isolated from user data."""
from pathlib import Path
import tempfile
import threading
from .engine import Folder, CATEGORIES, backup, transfer, digest, atomic_json


def self_test(report_path):
    with tempfile.TemporaryDirectory(prefix='devicebridge-selftest-') as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'restored'
        source.mkdir()
        target.mkdir()
        (source / 'sample.txt').write_text('DeviceBridge packaged-runtime integrity test.', encoding='utf-8')
        cancel = threading.Event()
        backed = backup(Folder(source), root / 'backups', set(CATEGORIES), cancel, lambda *args: None)
        folder = Path(backed['folder'])
        result = transfer(Folder(folder / 'files'), Folder(target), set(CATEGORIES), cancel, lambda *args: None, backup_folder=folder)
        if result['status'] != 'complete' or digest(source / 'sample.txt') != digest(target / 'sample.txt'):
            raise RuntimeError('Packaged runtime failed its round-trip integrity test.')
        from .media import MediaCache
        from PIL import Image
        import imageio_ffmpeg
        import subprocess
        import os
        Image.new('RGB', (180, 120), '#4b7788').save(source / 'sample.heic', format='HEIF')
        cache = MediaCache(root / 'preview-cache')
        image, _ = cache.image(Folder(source), 'sample.heic', cancel)
        assert image.size == (150, 108)
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=teal:s=160x120:d=0.3', '-c:v', 'libx264', str(source / 'sample.mp4')], check=True, timeout=30, creationflags=flags)
        video, _ = cache.image(Folder(source), 'sample.mp4', cancel)
        assert video.size == (150, 108)
        from .media import video_duration, play_frames
        assert video_duration(source / 'sample.mp4') > .2
        seek_times = []; seek_frames = []
        play_frames(source / 'sample.mp4', cancel, lambda frame: seek_frames.append(frame.size),
                    start=.1, position=seek_times.append, single=True)
        assert seek_frames == [(640,360)] and seek_times == [.1]
        from .clipboard_image import image_payloads
        dib_payload, png_payload = image_payloads(source/'sample.heic')
        assert dib_payload[:4] == b'\x28\x00\x00\x00'
        assert png_payload.startswith(b'\x89PNG\r\n\x1a\n')
        import io
        assert Image.open(io.BytesIO(png_payload)).size == (180,120)
        from .preview_canvas import PreviewCanvas
        import tkinter as tk
        window = tk.Tk(); window.withdraw(); window.attributes('-alpha',0)
        canvas = PreviewCanvas(window); canvas.pack(fill='both',expand=True)
        window.geometry('1000x700'); window.deiconify(); window.update()
        canvas.set_picture(Image.new('RGB',(1800,1200),'blue'))
        window.update()
        assert canvas.image is not None and canvas.image.width()>680 and canvas.picture.size == (1800,1200)
        window.destroy()
        from .app import App
        navigation_app = App(home=root/'navigation-ui'); navigation_app.withdraw()
        gallery = navigation_app.gallery
        gallery.source = Folder(source)
        gallery.items = [{'path':'sample.heic','album':'Fixture','kind':'Photos'},
                         {'path':'sample.mp4','album':'Fixture','kind':'Videos'}]
        gallery.enqueue = lambda *args: None
        gallery.open_preview(gallery.items[0])
        preview = gallery.preview; preview.attributes('-alpha',0)
        navigation_app.update()
        assert gallery.previous_button.cget('state') == 'disabled'
        gallery.next_button.invoke()
        assert gallery.preview is preview and gallery.preview_item['kind'] == 'Videos'
        assert gallery.next_button.cget('state') == 'disabled'
        gallery.previous_button.invoke()
        assert gallery.preview_item['kind'] == 'Photos'
        gallery.close_preview()
        gallery.render()
        from types import SimpleNamespace
        selected = tk.BooleanVar(master=navigation_app)
        gallery.select_media_click('sample.heic',SimpleNamespace(state=0),selected)
        gallery.select_media_click('sample.mp4',SimpleNamespace(state=1),selected)
        assert gallery.chosen == {'sample.heic','sample.mp4'}
        gallery.select_media_click('sample.heic',SimpleNamespace(state=4),selected)
        assert gallery.chosen == {'sample.mp4'}
        navigation_app.destroy()
        from .backup_catalog import BackupCatalog
        from .duplicates import find_duplicates, validate_removals
        catalog_home = root / 'catalog'
        catalog_home.mkdir()
        catalog = BackupCatalog(catalog_home)
        entry = catalog.add(folder)
        catalog.verify(entry, cancel, lambda *args: None)
        assert len(catalog.rows()) == 1
        groups = find_duplicates([{'id':'a','name':'Fixture','detail':'+256700123456'}, {'id':'b','name':'Fixture','detail':'00256700123456'}])
        assert len(groups) == 1
        assert validate_removals(groups, {'b'}) == {'b'}
        from .desktop import resource_path, create_shortcut
        from .wireless import endpoint, parse_services, candidates
        assert endpoint('192.168.1.20:37123') == '192.168.1.20:37123'
        nearby = candidates(parse_services('fixture _adb-tls-pairing._tcp 192.168.1.20:37123\nfixture-connect _adb-tls-connect._tcp 192.168.1.20:44444'), [])
        assert len(nearby) == 1 and nearby[0]['pair_address'].endswith(':37123') and nearby[0]['connect_address'].endswith(':44444')
        from .qr_pairing import new_session, image as qr_image
        qr = new_session()
        rendered = qr_image(qr)
        assert rendered.width == rendered.height and rendered.width > 200
        from zeroconf import Zeroconf, IPVersion
        # Runtime/socket smoke check on loopback only; no real phone discovery.
        with Zeroconf(interfaces=['127.0.0.1'], ip_version=IPVersion.V4Only):
            pass
        wireless_tools = False
        from .companion_link import Link
        local_link=Link('127.0.0.1')
        try:
            assert len(local_link.fingerprint)==64 and local_link.uri().startswith('twistbridge://connect?')
            import qrcode
            assert qrcode.make(local_link.uri()).get_image().width>200
        finally:
            local_link.close()
        if getattr(__import__('sys'), 'frozen', False):
            from .android_tools import resolve_adb
            embedded = resource_path('android/adb.exe')
            assert Path(resolve_adb({'adb': 'C:/missing-old-sdk/adb.exe'})) == embedded
            clean_env = dict(os.environ, PATH=str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'))
            subprocess.run([resolve_adb(), 'version'], check=True, capture_output=True, creationflags=flags, timeout=15, env=clean_env)
            help_text = subprocess.run([resolve_adb(), 'help'], check=True, capture_output=True, creationflags=flags, timeout=15, env=clean_env)
            assert b'pair' in help_text.stdout + help_text.stderr
            assert b'mdns' in help_text.stdout + help_text.stderr
            wireless_tools = True
            create_shortcut(__import__('sys').executable, root)
            assert (root / 'Twist MediaBridge.lnk').is_file()
        atomic_json(Path(report_path), {'status': 'passed', 'runtime': 'packaged' if getattr(__import__('sys'), 'frozen', False) else 'python', 'backup_files': backed['copied'], 'restored_files': result['copied'], 'sha256_match': True, 'heic_preview': True, 'video_thumbnail': True, 'video_seek': True, 'resizable_preview': True, 'preview_navigation': True, 'image_clipboard_payloads': True, 'range_selection': True, 'backup_manager': True, 'duplicate_finder': True, 'bundled_adb_and_shortcut': bool(getattr(__import__('sys'), 'frozen', False)), 'wireless_pairing_tools': wireless_tools, 'qr_generation': True, 'direct_discovery_runtime': True, 'companion_tls_runtime':True, 'companion_phone_hardware_tested':False, 'wireless_hardware_tested': False})
