"""Compile archived V36 source with externally supplied locked V29 assets.

This optional compiler entry does not sign, publish, install, access credentials
or rebuild a runtime payload. Source preparation never invokes this program.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def digest(raw):return hashlib.sha256(raw).hexdigest()
def pinned(row):
 p=ROOT/row['repository_path'];assert p.resolve().is_relative_to(ROOT.resolve())
 raw=p.read_bytes();assert digest(raw)==row['sha256']and len(raw)==row['bytes']
 return p

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 lock=json.loads((HERE/'source-lock.json').read_text('utf8'))
 assert lock['V']==36 and lock['parent_source_commit']=='f10bed302ecfbd8fe7106e85debd8c5de484db78'
 files={r['logical_name']:pinned(r)for r in lock['native_build_inputs']}
 asset_lock=json.loads(pinned(lock['external_asset_lock']).read_bytes())
 assert digest(args.assets.read_bytes())==asset_lock['sha256'],'External build assets differ'
 assert not args.output.exists(),'Do not overwrite a previous launcher'
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='els-v36-source-build-')as folder:
  root=Path(folder)
  with zipfile.ZipFile(args.assets)as archive:
   assert set(archive.namelist())=={r['path']for r in asset_lock['files']}
   for row in asset_lock['files']:
    assert row['path']in('ruben.png','launcher.ico')
    raw=archive.read(row['path']);assert len(raw)==row['size']and digest(raw)==row['sha256'];(root/row['path']).write_bytes(raw)
  compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  names=['Program.cs','AutoUpdate.cs','Diagnostics.cs','LauncherBootstrapDiagnostics.cs','MotionControls.cs','MainDesign.cs','RegisterDesign.cs','DesignProof.cs','ComponentRuntime.cs','LocalMode.cs']
  refs=['System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll']
  command=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(args.output.resolve()),'/win32icon:'+str(root/'launcher.ico'),'/win32manifest:'+str(files['app.manifest']),'/resource:'+str(files['runtime-files.signed.json'])+',ElsFriends.RuntimeFiles','/resource:'+str(root/'ruben.png')+',ElsFriends.Ruben',*['/reference:'+r for r in refs],*[str(files[n])for n in names]]
  subprocess.run(command,check=True)
 print(json.dumps(dict(path=str(args.output.resolve()),sha256=digest(args.output.read_bytes()),signed=False,installed=False,published=False,bit_identical_to_historical_binary_claimed=False)))

if __name__=='__main__':main()
