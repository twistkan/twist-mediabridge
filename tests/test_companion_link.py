import base64
import hashlib
import http.client
import json
from pathlib import Path
import ssl
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit

from bridge.companion_link import Link, Companion, retain_companions, windows_media_path
from bridge.engine import Cancelled, Folder, backup, load_manifest, transfer, digest
from bridge.contacts_bridge import load_contacts, export_vcards
from bridge.phone_backup import save_selected_contacts, backup_app_file, restore_app_file


class Phone:
    """Protocol fixture using real HTTPS, not a mocked Link.request."""
    def __init__(self, link):
        self.link=link
        self.token=link.enrollment
        self.context=ssl.create_default_context(cafile=str(Path(link.temp.name)/'cert.pem'))
        self.context.check_hostname=False
        self.data=b'fixture photo bytes\x00'*70000
        self.uploads={}
        self.operations=[]
        self.install_result={'status':'installed', 'message':'Android confirmed installation'}
        self.stop=threading.Event()
        self.token=self.post('/join',{'model':'Android 9 fixture'})[1]['token']
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def post(self,path,body,token=None):
        connection=http.client.HTTPSConnection('127.0.0.1',self.link.port,context=self.context,timeout=5)
        try:
            connection.request('POST',path,json.dumps(body),{'Authorization':'Bearer '+(self.token if token is None else token),'Content-Type':'application/json'})
            response=connection.getresponse()
            return response.status,json.loads(response.read())
        finally:connection.close()

    def operation(self,operation,args):
        self.operations.append(operation)
        if operation=='files':return [{'path':'DCIM/photo.jpg','size':len(self.data),'modified':123}]
        if operation=='info':return {'size':len(self.data),'sha256':hashlib.sha256(self.data).hexdigest()}
        if operation=='read':return base64.b64encode(self.data[args['offset']:args['offset']+args['size']]).decode()
        if operation=='thumbnail':
            import io
            from PIL import Image
            out=io.BytesIO();Image.new('RGB',(256,256),'teal').save(out,format='JPEG')
            return base64.b64encode(out.getvalue()).decode()
        if operation=='upload_begin':self.uploads['fixture']=bytearray();return 'fixture'
        if operation=='install_upload_begin':
            identity='apk-'+str(len(self.uploads));self.uploads[identity]=bytearray();return identity
        if operation=='install_prepare':
            for identity in args['ids']:
                if identity not in self.uploads:raise OSError('Missing APK part')
            return 'install-fixture'
        if operation=='install_status':return self.install_result
        if operation=='install_release':return True
        if operation=='upload_chunk':self.uploads[args['id']].extend(base64.b64decode(args['data']));return True
        if operation=='upload_finish':return 'copied'
        if operation=='upload_abort':return True
        if operation=='contacts':return [{'contact_id':'1','lookup':'fixture','name':'Fixture Person','numbers':['12345']}]
        if operation=='vcard':return base64.b64encode(b'BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Fixture Person\r\nTEL:12345\r\nEND:VCARD\r\n').decode()
        if operation=='app_files':return [{'path':'Apps/com.fixture.app/base.apk','size':len(self.data),'modified':123}]
        raise OSError('Unsupported fixture operation')

    def run(self):
        while not self.stop.is_set():
            try:
                code,response=self.post('/poll',{})
                if code!=200:return
                job=response['job']
                if job:
                    try:result={'value':self.operation(job['operation'],job['arguments'])}
                    except Exception as error:result={'error':str(error)}
                    self.post('/result',{'id':job['id'],'result':result})
            except (OSError,ssl.SSLError):return

    def close(self):
        self.stop.set();self.thread.join(3)


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.link=Link('127.0.0.1')
        self.addCleanup(self.link.close)

    def phone(self):
        phone=Phone(self.link);self.addCleanup(phone.close);return phone

    def test_install_single_apk_waits_for_android_and_cleans_staging(self):
        fixture=self.phone();phone=Companion(self.link)
        with tempfile.TemporaryDirectory() as temp:
            apk=Path(temp)/'Example.apk';apk.write_bytes(b'APK fixture'*70000)
            result=restore_app_file(phone,apk,threading.Event(),lambda *a:None)
            self.assertIn('confirmed',result)
            self.assertEqual(bytes(fixture.uploads['apk-0']),apk.read_bytes())
            self.assertIn('install_status',fixture.operations)
            self.assertIn('install_release',fixture.operations)
            self.assertIn('upload_abort',fixture.operations)
            self.assertNotIn('upload_finish',fixture.operations)

    def test_install_android_rejection_is_failure_not_success(self):
        fixture=self.phone();fixture.install_result={'status':'failed','message':'Incompatible Android version'}
        with tempfile.TemporaryDirectory() as temp:
            apk=Path(temp)/'Example.apk';apk.write_bytes(b'APK fixture')
            with self.assertRaisesRegex(OSError,'Incompatible Android version'):
                restore_app_file(Companion(self.link),apk,threading.Event(),lambda *a:None)
        self.assertIn('install_release',fixture.operations)

    def test_install_split_backup_transfers_all_verified_parts(self):
        fixture=self.phone();phone=Companion(self.link)
        with tempfile.TemporaryDirectory() as temp:
            saved=backup_app_file(phone,'com.fixture.app','Fixture',temp,threading.Event(),lambda *a:None)
            # Existing export fixture has one APK; build a genuine two-part archive.
            import zipfile
            apk=Path(temp)/'Fixture.apks'
            parts=[b'base fixture',b'split fixture']
            manifest={'format':'twist-apks-1','status':'complete','package':'com.fixture.app',
                      'files':[{'name':f'part-{i}.apk','sha256':hashlib.sha256(data).hexdigest()} for i,data in enumerate(parts)]}
            with zipfile.ZipFile(apk,'w') as archive:
                archive.writestr('app.json',json.dumps(manifest))
                for item,data in zip(manifest['files'],parts):archive.writestr(item['name'],data)
            self.assertIn('confirmed',restore_app_file(phone,apk,threading.Event(),lambda *a:None))
            self.assertEqual([bytes(data) for data in fixture.uploads.values()],parts)
            self.assertEqual(fixture.operations.count('install_upload_begin'),2)
            manifest['files'][0]['sha256']='0'*64
            with zipfile.ZipFile(apk,'w') as archive:
                archive.writestr('app.json',json.dumps(manifest))
                for item,data in zip(manifest['files'],parts):archive.writestr(item['name'],data)
            before=len(fixture.operations)
            with self.assertRaisesRegex(ValueError,'integrity'):
                restore_app_file(phone,apk,threading.Event(),lambda *a:None)
            self.assertEqual(len(fixture.operations),before)

    def test_install_cancel_releases_pending_request(self):
        fixture=self.phone();fixture.install_result={'status':'waiting'}
        cancel=threading.Event()
        with tempfile.TemporaryDirectory() as temp:
            apk=Path(temp)/'Example.apk';apk.write_bytes(b'APK fixture')
            def report(progress,message):
                if 'approve installation' in message:cancel.set()
            with self.assertRaises(Cancelled):
                restore_app_file(Companion(self.link),apk,cancel,report)
        self.assertIn('install_release',fixture.operations)

    def test_install_does_not_accept_non_apk_or_empty_set(self):
        self.phone();phone=Companion(self.link)
        with self.assertRaises(ValueError):phone.install_apks([],threading.Event(),lambda *a:None)

    def test_qr_is_pinned_expiring_and_one_use(self):
        data=parse_qs(urlsplit(self.link.uri()).query)
        self.assertEqual(data['fingerprint'][0],self.link.fingerprint)
        self.assertEqual(len(data['token'][0]),64)
        self.assertFalse(self.link.online())
        phone=self.phone()
        self.assertEqual(phone.post('/join',{'model':'Another phone'},token=data['token'][0])[0],403)
        self.assertEqual(phone.post('/heartbeat',{},token='invalid')[0],403)
        self.assertEqual(phone.post('/result',{'id':'not-pending','result':{'value':1}})[0],409)

    def test_expired_pairing_rejected(self):
        self.link.deadline=time.monotonic()-1
        with self.assertRaises(KeyError):Phone(self.link)
        self.assertFalse(self.link.joined)

    def test_real_https_multi_chunk_file_and_backup(self):
        fixture=self.phone();phone=Companion(self.link)
        self.assertEqual(list(phone.files({'Photos'},None)),[('DCIM/photo.jpg',len(fixture.data))])
        with tempfile.TemporaryDirectory() as folder:
            result=backup(phone,folder,{'Photos'},None,lambda *args:None)
            manifest=load_manifest(result['folder'])
            self.assertEqual(manifest['items'][0]['sha256'],hashlib.sha256(fixture.data).hexdigest())
            self.assertEqual((Path(result['folder'])/'files/DCIM/photo.jpg').read_bytes(),fixture.data)
            uploaded=Path(folder)/'send.jpg';uploaded.write_bytes(fixture.data)
            self.assertEqual(phone.write(uploaded,'Pictures/send.jpg',None)[1],'copied')
            self.assertEqual(bytes(fixture.uploads['fixture']),fixture.data)

    def test_native_vcards_and_apk_export(self):
        fixture=self.phone();phone=Companion(self.link)
        rows=load_contacts(phone,None,lambda *args:None)
        self.assertEqual(rows[0]['name'],'Fixture Person')
        self.assertIn(b'FN:Fixture Person',b''.join(export_vcards(phone,rows,None,lambda *args:None)))
        with tempfile.TemporaryDirectory() as folder:
            save_selected_contacts(rows,Path(folder)/'contacts.vcf',None,phone)
            output=backup_app_file(phone,'com.fixture.app','Fixture App',folder,None,lambda *args:None)
            self.assertEqual(output.name,'Fixture App.apk')
            self.assertEqual(output.read_bytes(),fixture.data)

    def test_offline_clears_access_and_discovery_keeps_active_companion(self):
        fixture=self.phone();phone=Companion(self.link)
        self.assertIn(phone,retain_companions([phone],[]))
        fixture.close()
        self.link.last_seen=time.monotonic()-16
        self.assertFalse(phone.online())
        self.assertNotIn(phone,retain_companions([phone],[]))
        with self.assertRaises(OSError):phone.call('files')

    def test_canceled_request_and_stale_response(self):
        fixture=self.phone();phone=Companion(self.link)
        fixture.close()
        cancel=threading.Event()
        result=[]
        def request():
            try:phone.call('files',cancel)
            except Exception as error:result.append(error)
        worker=threading.Thread(target=request);worker.start()
        deadline=time.monotonic()+3
        while not self.link.pending and time.monotonic()<deadline:time.sleep(.01)
        key=next(iter(self.link.pending))
        cancel.set();worker.join(3)
        self.assertIsInstance(result[0],Cancelled)
        self.assertFalse(self.link.pending)
        self.assertEqual(fixture.post('/result',{'id':key,'result':{'value':[]}})[0],409)

    def test_thumbnails_use_phone_cache_without_original_download(self):
        from bridge.media import MediaCache
        fixture=self.phone();phone=Companion(self.link)
        list(phone.files({'Photos'},None))
        with tempfile.TemporaryDirectory() as folder:
            cache=MediaCache(folder)
            first,_=cache.image(phone,'DCIM/photo.jpg',None,size=(132,132))
            second,_=cache.image(phone,'DCIM/photo.jpg',None,size=(132,132))
            self.assertEqual(first.size,second.size)
            self.assertEqual(fixture.operations.count('thumbnail'),1)
            self.assertNotIn('read',fixture.operations)

    def test_corrupt_download_is_not_published(self):
        fixture=self.phone();phone=Companion(self.link)
        original=fixture.operation
        def corrupted(operation,args):
            if operation=='read':return base64.b64encode(b'x'*args['size']).decode()
            return original(operation,args)
        fixture.operation=corrupted
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):phone.read('DCIM/photo.jpg',folder,None)
            self.assertFalse(list(Path(folder).iterdir()))

    def test_path_traversal_and_arbitrary_shell_are_blocked(self):
        self.phone();phone=Companion(self.link)
        with self.assertRaises(ValueError):phone.remote('../secret')
        with self.assertRaises(OSError):phone.shell('arbitrary shell',None)

    def test_disconnect_revokes_token(self):
        phone=self.phone()
        self.assertEqual(phone.post('/disconnect',{})[0],200)
        self.assertFalse(self.link.online())
        self.assertEqual(phone.post('/heartbeat',{})[0],403)

    def test_lost_poll_redelivers_same_request_without_losing_it(self):
        fixture=self.phone();fixture.close()
        job={'id':'retry-fixture','operation':'delete_media','arguments':{'path':'DCIM/photo.jpg'}}
        self.link.pending[job['id']]=[threading.Event(),None,job,0.0]
        self.assertEqual(self.link.next_job(),job)
        self.assertIsNone(self.link.next_job())
        self.link.pending[job['id']][3]-=6
        self.assertEqual(self.link.next_job(),job)
        self.assertEqual(fixture.post('/result',{'id':job['id'],'result':{'value':True}})[0],200)
        self.assertEqual(fixture.post('/result',{'id':job['id'],'result':{'value':False}})[0],200)
        self.assertEqual(self.link.pending[job['id']][1],{'value':True})
        self.assertIsNone(self.link.next_job())

    def test_heartbeat_keeps_session_active_without_media_activity(self):
        fixture=self.phone();fixture.close()
        for _ in range(3):
            self.link.last_seen=time.monotonic()-10
            self.assertEqual(fixture.post('/heartbeat',{})[0],200)
            self.assertTrue(self.link.online())
        self.link.last_seen=time.monotonic()-16
        self.assertEqual(fixture.post('/heartbeat',{})[0],403)
        self.assertFalse(self.link.online())

    def test_companion_media_delete_uses_approved_original_paths_not_adb(self):
        from bridge.delete_actions import delete_media
        from unittest.mock import Mock
        fixture=self.phone();phone=Companion(self.link)
        native=fixture.operation
        selected='0/DCIM/Camera/photo:one.jpg'
        failed='0/DCIM/Camera/locked.mp4'
        deleted=[]
        def operation(kind,args):
            if kind=='files':return [{'path':p,'size':12,'modified':1} for p in [selected,failed,'0/DCIM/Camera/unselected.jpg']]
            if kind=='delete_media':
                deleted.append(args['path'])
                if args['path']==failed:raise OSError('Folder write access denied')
                return True
            return native(kind,args)
        fixture.operation=operation
        list(phone.files({'Photos','Videos'},None))
        phone.shell=Mock(side_effect=AssertionError('Companion must never use an ADB shell'))
        result=delete_media(phone,[windows_media_path(selected),failed],None,lambda *a:None)
        self.assertEqual(deleted,[selected,failed])
        self.assertTrue(result[0][1]);self.assertFalse(result[1][1])
        self.assertIn('write access denied',result[1][2])
        phone.shell.assert_not_called()

    def test_companion_delete_validates_entire_selection_before_requests(self):
        from bridge.delete_actions import delete_media
        fixture=self.phone();phone=Companion(self.link)
        with self.assertRaises(ValueError):delete_media(phone,['DCIM/photo.jpg','Documents/keep.txt'],None,lambda *a:None)
        with self.assertRaises(ValueError):delete_media(phone,['DCIM/photo.jpg','../escape.jpg'],None,lambda *a:None)
        self.assertNotIn('delete_media',fixture.operations)

    def test_companion_delete_cancelled_before_request(self):
        from bridge.delete_actions import delete_media
        fixture=self.phone();phone=Companion(self.link)
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):delete_media(phone,['DCIM/photo.jpg'],cancel,lambda *a:None)
        self.assertNotIn('delete_media',fixture.operations)

    def test_many_item_transfer_keeps_staging_bounded_and_session_alive(self):
        fixture=self.phone();phone=Companion(self.link)
        fixture.data=b'batch-fixture'*12000
        paths=[f'0/DCIM/Camera/photo-{i:03}.jpg' for i in range(24)]
        native=fixture.operation
        def operation(kind,args):
            if kind=='files':return [{'path':path,'size':len(fixture.data),'modified':1} for path in paths]
            return native(kind,args)
        fixture.operation=operation
        real_read=phone.read
        counts=[]
        def read(name,temp,cancel):
            counts.append(len(list(Path(temp).iterdir())))
            self.assertTrue(self.link.online())
            return real_read(name,temp,cancel)
        phone.read=read
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            (target/'photo-003.jpg').write_bytes(b'preserve existing file')
            result=transfer(phone,Folder(target),{'Photos'},None,lambda *a:None,flatten=True)
            self.assertEqual((result['copied'],result['failed']),(23,1))
            self.assertEqual(counts,[0]*24)
            self.assertEqual((target/'photo-003.jpg').read_bytes(),b'preserve existing file')
            self.assertEqual(digest(target/'photo-023.jpg'),hashlib.sha256(fixture.data).hexdigest())
            self.assertTrue(self.link.online())

    def test_large_file_transfer_spans_many_chunks_without_disconnect(self):
        fixture=self.phone();phone=Companion(self.link)
        fixture.data=b'video-test'*900000
        with tempfile.TemporaryDirectory() as folder:
            result=transfer(phone,Folder(folder),{'Videos'},None,lambda *a:None,paths=['DCIM/large.mp4'],flatten=True)
            self.assertEqual(result['copied'],1)
            self.assertGreater(fixture.operations.count('read'),16)
            self.assertEqual(digest(Path(folder)/'large.mp4'),hashlib.sha256(fixture.data).hexdigest())
            self.assertTrue(self.link.online())

    def test_android_only_names_have_stable_windows_aliases(self):
        from bridge.engine import safe_relative,category
        for name in ['primary:/DCIM/photo.jpg','DCIM/a:b.jpg','DCIM/CON.jpg','DCIM/trailing /photo.jpg','DCIM/a\\b.jpg']:
            alias=windows_media_path(name)
            safe_relative(alias)
            self.assertEqual(alias,windows_media_path(name))
            self.assertEqual(category(alias),'Photos')
        self.assertNotEqual(windows_media_path('DCIM/a:b.jpg'),windows_media_path('DCIM/a?b.jpg'))
        self.assertEqual(windows_media_path('DCIM/Camera/normal.jpg'),'DCIM/Camera/normal.jpg')
        for name in ['../secret.jpg','/DCIM/photo.jpg','DCIM/../photo.jpg','DCIM//photo.jpg']:
            with self.assertRaises(ValueError):windows_media_path(name)

    def test_unsafe_root_does_not_block_album_or_verified_backup(self):
        fixture=self.phone();phone=Companion(self.link)
        original=fixture.operation
        remote='primary:/Camera/photo:2026.jpg'
        def response(operation,args):
            if operation=='files':return [{'path':remote,'size':len(fixture.data),'modified':123}, {'path':'DCIM/normal.jpg','size':len(fixture.data),'modified':123}]
            if operation in ('info','read','thumbnail'):
                self.assertIn(args['path'],[remote,'DCIM/normal.jpg'])
            return original(operation,args)
        fixture.operation=response
        with tempfile.TemporaryDirectory() as folder:
            result=backup(phone,folder,{'Photos'},None,lambda *args:None)
            manifest=load_manifest(result['folder'])
            self.assertEqual(len(manifest['items']),2)
            alias=windows_media_path(remote)
            self.assertEqual(phone.remote(alias),remote)
            self.assertEqual((Path(result['folder'])/'files'/alias).read_bytes(),fixture.data)
            self.assertTrue(phone.scan_warnings)


if __name__=='__main__':unittest.main()
