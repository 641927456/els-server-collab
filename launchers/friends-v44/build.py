"""Compile exact V44 source and existing signed resources; never sign or deploy."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def sha(path):
    with Path(path).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def bound(root,name):
    p=PurePosixPath(name)
    if p.is_absolute()or '\\'in name or ':'in name or any(x in ('','.','..')for x in name.split('/')):raise ValueError('Unsafe build source')
    result=root.joinpath(*p.parts)
    if not result.resolve().is_relative_to(root.resolve()):raise ValueError('Build source escaped root')
    for item in (result,*result.parents):
        if item==root.parent:break
        if item.is_symlink()or(getattr(item,'is_junction',lambda:False)()):raise ValueError('Linked build source')
    return result

def inputs(root=None):
    root=Path(root)if root is not None else ROOT
    archive=root/'launchers/friends-v44';lock=json.loads((archive/'source-lock.json').read_bytes());files={}
    for row in lock['native_build_inputs']:
        name=row['logical_name'];bound(archive,name)
        if name in files:raise ValueError('Duplicate build input')
        path=bound(root,row['source'])
        if path.stat().st_size!=row['size']or sha(path)!=row['sha256']:raise ValueError('Changed build input: '+name)
        files[name]=path
    required={row['logical_name']for row in lock['resources']if 'logical_name'in row}
    if not required<=files.keys()or len(lock['resources'])!=9:raise ValueError('Missing embedded resource')
    if len([n for n in files if n.endswith('.cs')])!=14 or 'app.manifest'not in files:raise ValueError('Native source set differs')
    artwork=lock['external_asset_lock'];path=bound(root,artwork['source'])
    if sha(path)!=artwork['sha256']:raise ValueError('Artwork lock changed')
    return lock,files,json.loads(path.read_bytes())

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');parser.add_argument('--assets',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    lock,files,assets=inputs()
    if args.check_only:print(json.dumps(dict(ok=True,V=44,mapped_sources=len(files),embedded_resources=9,compiled=False,published=False)));return
    if not(args.assets and args.output):parser.error('--assets and --output are required')
    if sha(args.assets)!=assets['sha256']:raise ValueError('Artwork archive changed')
    if args.output.exists():raise ValueError('Output already exists')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='v44-build-',dir=args.output.parent)as folder:
        temp=Path(folder)
        with zipfile.ZipFile(args.assets)as archive:
            if len(archive.infolist())!=len(assets['files'])or set(archive.namelist())!={r['path']for r in assets['files']}:raise ValueError('Artwork membership changed')
            for row in assets['files']:
                if row['path']not in ('ruben.png','launcher.ico'):raise ValueError('Unsafe artwork')
                raw=archive.read(row['path'])
                if len(raw)!=row['size']or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Artwork checksum changed')
                (temp/row['path']).write_bytes(raw)
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        refs=['System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll']
        command=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(args.output.resolve()),'/win32icon:'+str(temp/'launcher.ico'),'/win32manifest:'+str(files['app.manifest'])]
        for row in lock['resources']:
            path=files[row['logical_name']]if'logical_name'in row else temp/row['external_asset']
            if sha(path)!=row['sha256']:raise ValueError('Embedded resource changed')
            command.append('/resource:'+str(path)+','+row['name'])
        command+=['/reference:'+r for r in refs]+[str(p)for n,p in sorted(files.items())if n.endswith('.cs')]
        subprocess.run(command,check=True,env=dict(os.environ,TEMP=str(temp),TMP=str(temp)),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print(json.dumps(dict(ok=True,sha256=sha(args.output),release_metadata_signed=False,published=False,exact_PE_reproduction_claimed=False)))
if __name__=='__main__':main()
