"""Install only SHA-locked non-source runtime assets; never import saves or credentials."""
from pathlib import Path
import argparse,hashlib,json,os,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--repair',action='store_true',help='Explicitly replace changed locked assets, never source or state')
    args=parser.parse_args(argv)
    lock=json.loads((ROOT/'runtime-assets.lock.json').read_text(encoding='utf8'))
    if digest(args.archive)!=lock['archive_sha256']:raise ValueError('Runtime archive SHA256 mismatch')
    installed=0;unchanged=0
    with zipfile.ZipFile(args.archive) as archive:
        for row in lock['files']:
            name=row['path'];relative=Path(name)
            allowed=name.startswith(('python/','vendor/','tools/pylibs/','analysis/','launcher/assets/')) or name in {'els_server/data/client/catalog.sqlite3','本地测试启动器.exe'}
            if not allowed or relative.is_absolute() or '..' in relative.parts:raise ValueError('Unexpected runtime asset path')
            target=ROOT/relative
            if not target.resolve().is_relative_to(ROOT):raise ValueError('Runtime path escapes repository')
            parent=target.parent
            while parent!=ROOT:
                if parent.is_symlink() or parent.is_junction():raise ValueError('Runtime parent is a linked directory')
                parent=parent.parent
            if target.is_symlink() or target.is_junction():raise ValueError('Runtime target is linked')
            entry=archive.getinfo(lock['zip_root']+'/'+name)
            if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Linked archive member')
            if entry.file_size!=row['size']:raise ValueError('Asset size mismatch: '+name)
            if target.exists():
                if target.is_file() and target.stat().st_size==row['size'] and digest(target)==row['sha256']:
                    unchanged+=1;continue
                if not args.repair:raise ValueError('Existing asset differs; refusing overwrite: '+name)
            target.parent.mkdir(parents=True,exist_ok=True)
            data=archive.read(entry)
            if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Asset SHA256 mismatch: '+name)
            handle=tempfile.NamedTemporaryFile(prefix='.runtime-',dir=target.parent,delete=False)
            temporary=Path(handle.name)
            try:
                with handle:handle.write(data)
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
            installed+=1
    cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
    (cache/'installed.json').write_text(json.dumps(dict(release=lock['release'],archive_sha256=lock['archive_sha256'],installed=installed,unchanged=unchanged),indent=2),encoding='utf8')
    print(json.dumps(dict(ok=True,installed=installed,unchanged=unchanged,accounts_or_saves_imported=False)))

if __name__=='__main__':main()
