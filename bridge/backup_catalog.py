"""Local backup index and integrity checks; forgetting an entry never deletes files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from .engine import atomic_json, contained, digest, load_manifest, check_cancel, Folder, Android, CATEGORIES, transfer, Cancelled
from .phone_backup import validate_vcard, restore_app_file, restore_vcard


def describe(path):
    path=Path(path).resolve()
    if path.is_file():
        suffix=path.suffix.lower()
        if suffix=='.vcf':kind,count='Contacts',validate_vcard(path)
        elif suffix=='.apk':
            with zipfile.ZipFile(path) as archive:
                if 'AndroidManifest.xml' not in archive.namelist():raise ValueError('Not an Android APK.')
            kind,count='App',1
        elif suffix=='.apks':
            with zipfile.ZipFile(path) as archive:
                if archive.getinfo('app.json').file_size>1024*1024:raise ValueError('Invalid app manifest.')
                data=json.loads(archive.read('app.json'))
                if data.get('format')!='twist-apks-1' or data.get('status')!='complete':raise ValueError('Not a completed app archive.')
            kind,count='App bundle',1
        else:raise ValueError('Choose a .vcf, .apk, .apks or completed backup folder.')
        fingerprints=[{'name':'.','sha256':digest(path),'size':path.stat().st_size}]
        size=path.stat().st_size
    elif path.is_dir():
        if (path/'manifest.json').is_file():
            data=load_manifest(path)
            kind,count='Files',len(data['items'])
            fingerprints=[{'name':'manifest.json','sha256':digest(path/'manifest.json')}]
            size=sum(item['size'] for item in data['items'])
        elif (path/'app.json').is_file():
            data=json.loads((path/'app.json').read_text(encoding='utf-8'))
            if data.get('format')!='twist-apks-1' or data.get('status')!='complete':raise ValueError('Not a completed app backup.')
            kind,count='App folder',1
            fingerprints=[{'name':'app.json','sha256':digest(path/'app.json')}]
            size=sum(contained(path,item['name']).stat().st_size for item in data['files'])
        else:
            files=sorted(path.iterdir())
            if not files or any(not file.is_file() or file.suffix.lower()!='.vcf' or file.is_symlink() for file in files):
                raise ValueError('Folder is not a recognized backup.')
            kind='Contact files'
            count=sum(validate_vcard(file) for file in files)
            fingerprints=[{'name':file.name,'sha256':digest(file),'size':file.stat().st_size} for file in files]
            size=sum(file.stat().st_size for file in files)
    else:raise ValueError('Backup location is missing.')
    return {'id':hashlib.sha256(str(path).casefold().encode()).hexdigest(),'path':str(path),'name':path.name,
            'kind':kind,'count':count,'size':size,'date':datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            'fingerprints':fingerprints,'check':'Not checked'}


class BackupCatalog:
    def __init__(self,home):
        self.file=Path(home)/'backup-catalog.json'

    def rows(self):
        try:data=json.loads(self.file.read_text(encoding='utf-8'))
        except (OSError,ValueError):data=[]
        if not isinstance(data,list):return []
        data=[row for row in data if isinstance(row,dict) and all(key in row for key in ('id','path','name','kind','count','size','date','check'))]
        return sorted(data,key=lambda row:row.get('date',''),reverse=True)

    def add(self,path):
        path=str(Path(path).resolve())
        rows=self.rows()
        found=next((row for row in rows if row['path'].casefold()==path.casefold()),None)
        if found:return found
        row=describe(path)
        rows.append(row)
        atomic_json(self.file,rows)
        return row

    def scan(self,folder,cancel,report):
        folder=Path(folder)
        before=len(self.rows())
        try:
            check_cancel(cancel)
            self.add(folder)
            return f'{len(self.rows())-before} backups added · {len(self.rows())} in manager'
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):pass
        candidates=[folder]
        if folder.is_dir():
            for index,child in enumerate(folder.iterdir()):
                if index>=1000:break
                if not child.name.startswith('.') and not child.is_symlink() and not (hasattr(child,'is_junction') and child.is_junction()):
                    candidates.append(child)
        for index,path in enumerate(candidates):
            check_cancel(cancel)
            report(index/max(1,len(candidates)),f'Checking backup locations {index+1}/{len(candidates)}')
            try:self.add(path)
            except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):pass
        return f'{len(self.rows())-before} backups added · {len(self.rows())} in manager'

    def forget(self,key):
        atomic_json(self.file,[row for row in self.rows() if row['id']!=key])

    def verify(self,row,cancel,report):
        try:
            verify_backup(row,cancel,report)
            state='Verified '+datetime.now().strftime('%Y-%m-%d %H:%M')
        except Cancelled:
            self._state(row['id'],'Check cancelled')
            raise
        except Exception:
            self._state(row['id'],'Changed / unavailable')
            raise
        self._state(row['id'],state)
        return 'Backup verified. Stored checksums match the recorded files.'

    def _state(self,key,state):
        rows=self.rows()
        for row in rows:
            if row['id']==key:row['check']=state
        atomic_json(self.file,rows)

    def mark_verified(self,key):
        self._state(key,'Verified '+datetime.now().strftime('%Y-%m-%d %H:%M'))


def verify_backup(row,cancel,report):
    path=Path(row['path'])
    if not path.exists():raise ValueError('Backup location is missing. Reconnect its drive or add its new location.')
    fingerprints=row.get('fingerprints',[])
    if not fingerprints:raise ValueError('No recorded checksums. Remove this entry from the list and add the backup again.')
    for index,item in enumerate(fingerprints):
        check_cancel(cancel)
        report(index/max(1,len(fingerprints)),'Verifying backup checksums…')
        file=path if item['name']=='.' else contained(path,item['name'])
        if digest(file,cancel)!=item['sha256']:raise ValueError('Backup has changed since it was added. Restore was not started.')
    if row['kind']=='Files':
        data=load_manifest(path)
        for index,item in enumerate(data['items']):
            check_cancel(cancel)
            report(index/max(1,len(data['items'])),'Verifying saved files…')
            file=contained(path/'files',item['path'])
            if file.stat().st_size!=item['size'] or digest(file,cancel)!=item['sha256']:raise ValueError('Saved file integrity check failed.')
    elif row['kind']=='App folder':
        data=json.loads((path/'app.json').read_text(encoding='utf-8'))
        for item in data['files']:
            if digest(contained(path,item['name']),cancel)!=item['sha256']:raise ValueError('App backup integrity check failed.')
    elif row['kind']=='App bundle':
        with zipfile.ZipFile(path) as archive:
            data=json.loads(archive.read('app.json'))
            for item in data['files']:
                check_cancel(cancel)
                # Validate names without extracting anything to disk.
                contained(path.parent,item['name'])
                checksum=hashlib.sha256()
                with archive.open(item['name']) as stream:
                    while chunk:=stream.read(1024*1024):
                        check_cancel(cancel)
                        checksum.update(chunk)
                if checksum.hexdigest()!=item['sha256']:raise ValueError('Split APK integrity check failed.')
    elif row['kind']=='Contacts':validate_vcard(path)
    elif row['kind']=='Contact files':
        actual={p.name for p in path.iterdir() if p.is_file() and p.suffix.lower()=='.vcf'}
        if actual!={item['name'] for item in fingerprints}:raise ValueError('Contact backup folder contents have changed.')
        for item in fingerprints:validate_vcard(contained(path,item['name']))
    report(1,'Backup verified')


def restore_backup(row,target,cancel,report):
    verify_backup(row,cancel,report)
    path=Path(row['path'])
    if row['kind']=='Files':
        result=transfer(Folder(path/'files'),target,set(CATEGORIES),cancel,report,backup_folder=path)
        return f"{result['copied']} files restored · {result['present']} already present · {result['failed']} conflicts/errors"
    if not isinstance(target,Android):raise ValueError('Choose an authorized Android phone for app or contact restore.')
    if row['kind'].startswith('App'):return restore_app_file(target,path,cancel,report)
    if row['kind']=='Contacts':return restore_vcard(target,path,cancel)
    if row['kind']=='Contact files':
        with tempfile.TemporaryDirectory(prefix='twist-restore-contacts-') as temp:
            combined=Path(temp)/'contacts.vcf'
            with combined.open('wb') as out:
                for item in row['fingerprints']:
                    check_cancel(cancel)
                    out.write(contained(path,item['name']).read_bytes().rstrip(b'\r\n')+b'\r\n')
            return restore_vcard(target,combined,cancel)
    raise ValueError('Unknown backup type.')
