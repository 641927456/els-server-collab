"""Compile pinned V43 source and signed manifests with locked artwork; never sign or deploy."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def inputs():
    lock=json.loads((HERE/'source-lock.json').read_bytes());files={}
    for row in lock['native_build_inputs']:
        name=row['logical_name']
        if Path(name).name!=name or name in files:raise ValueError('Unsafe build input')
        p=HERE/name
        if p.is_symlink() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:raise ValueError('Build input differs: '+name)
        files[name]=p
    if set(p.name for p in HERE.glob('*.cs'))!={n for n in files if n.endswith('.cs')}:raise ValueError('C# source set differs')
    for name in ('local_bootstrap.py','local_updater.py','runtime-files.signed.json','local-runtime-files.signed.json'):
        if name not in files:raise ValueError('Missing embedded resource')
    asset=lock['external_asset_lock'];p=HERE/asset['logical_name']
    if sha(p)!=asset['sha256']:raise ValueError('Artwork lock differs')
    return lock,files,json.loads(p.read_bytes())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');parser.add_argument('--assets',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    lock,files,assets=inputs()
    if args.assets and sha(args.assets)!=assets['sha256']:raise ValueError('Artwork archive differs')
    if args.check_only:
        print(json.dumps({'ok':True,'V':43,'source_files':len(files),'compiled':False,'published':False}));return
    if not(args.assets and args.output):parser.error('--assets and --output are required')
    if args.output.exists():raise ValueError('Output already exists')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='v43-build-',dir=args.output.parent) as folder:
        temporary=Path(folder)
        with zipfile.ZipFile(args.assets) as archive:
            if set(archive.namelist())!={r['path'] for r in assets['files']}:raise ValueError('Artwork member set differs')
            for row in assets['files']:
                if row['path'] not in ('ruben.png','launcher.ico'):raise ValueError('Unsafe artwork path')
                raw=archive.read(row['path'])
                if len(raw)!=row['size'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Artwork checksum differs')
                (temporary/row['path']).write_bytes(raw)
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        refs=['System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll']
        resources=[(files['runtime-files.signed.json'],'ElsFriends.RuntimeFiles'),(files['local-runtime-files.signed.json'],'ElsFriends.LocalRuntimeFiles'),(files['local_bootstrap.py'],'ElsFriends.LocalBootstrap'),(files['local_updater.py'],'ElsFriends.LocalUpdater'),(temporary/'ruben.png','ElsFriends.Ruben'),(files['legacy-local-runtime-files.signed.json'],'ElsFriends.LegacyLocalRuntimeFiles'),(files['legacy-local-bootstrap.py'],'ElsFriends.LegacyLocalBootstrap')]
        command=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(args.output.resolve()),'/win32icon:'+str(temporary/'launcher.ico'),'/win32manifest:'+str(files['app.manifest'])]
        command+=['/resource:'+str(path)+','+name for path,name in resources]+['/reference:'+name for name in refs]+[str(p)for name,p in sorted(files.items())if name.endswith('.cs')]
        subprocess.run(command,check=True)
    print(json.dumps({'ok':True,'path':str(args.output),'sha256':sha(args.output),'release_metadata_signed':False,'published':False}))

if __name__=='__main__':main()
