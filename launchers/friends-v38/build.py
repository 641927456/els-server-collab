"""Compile archived source with SHA-locked external assets; never sign or deploy."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent
def digest(raw):return hashlib.sha256(raw).hexdigest()
def inputs():
    lock=json.loads((HERE/'source-lock.json').read_bytes());files={}
    for row in lock['native_build_inputs']:
        name=row['logical_name'];assert Path(name).name==name and name not in files
        p=HERE/name;raw=p.read_bytes();assert len(raw)==row['bytes'] and digest(raw)==row['sha256'],name
        files[name]=p
    assert set(p.name for p in HERE.glob('*.cs'))=={n for n in files if n.endswith('.cs')}
    assert ('local_updater.py' in files)==(lock['V']==38)
    asset=lock['external_asset_lock'];p=HERE/asset['logical_name'];assert digest(p.read_bytes())==asset['sha256']
    return lock,files,json.loads(p.read_bytes())
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');parser.add_argument('--assets',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    lock,files,assets=inputs()
    if args.assets:
        assert digest(args.assets.read_bytes())==assets['sha256'],'External asset archive differs'
    if args.check_only:
        print(json.dumps(dict(ok=True,V=lock['V'],native_inputs=len(files),external_assets_checked=bool(args.assets),compiled=False,installed=False)));return
    parser.error('--assets and --output are required') if not(args.assets and args.output) else None
    assert not args.output.exists(),'Do not overwrite a launcher'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='els-archived-launcher-')as folder:
        temporary=Path(folder)
        with zipfile.ZipFile(args.assets)as archive:
            assert set(archive.namelist())=={r['path']for r in assets['files']}
            for row in assets['files']:
                assert row['path']in ('ruben.png','launcher.ico')
                raw=archive.read(row['path']);assert len(raw)==row['size'] and digest(raw)==row['sha256'];(temporary/row['path']).write_bytes(raw)
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        refs=['System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll']
        resources=['/resource:'+str(files['runtime-files.signed.json'])+',ElsFriends.RuntimeFiles','/resource:'+str(temporary/'ruben.png')+',ElsFriends.Ruben']
        if lock['V']==38:resources.append('/resource:'+str(files['local_updater.py'])+',ElsFriends.LocalUpdater')
        command=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(args.output.resolve()),'/win32icon:'+str(temporary/'launcher.ico'),'/win32manifest:'+str(files['app.manifest']),*resources,*['/reference:'+r for r in refs],*[str(p)for n,p in sorted(files.items())if n.endswith('.cs')]]
        subprocess.run(command,check=True)
    print(json.dumps(dict(path=str(args.output.resolve()),sha256=digest(args.output.read_bytes()),release_metadata_signed=False,published=False,installed=False,historical_binary_identity_claimed=False)))
if __name__=='__main__':main()
