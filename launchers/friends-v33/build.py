"""Build the small Windows launcher; no signing key, server or player state used."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,zipfile
HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 lock=json.loads((HERE/'build-assets.lock.json').read_text('utf8'));assert digest(a.assets)==lock['sha256'],'Build asset archive differs'
 assert not a.output.exists(),'Do not overwrite a previously built launcher';a.output.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='els-v33-build-') as folder:
  root=Path(folder)
  with zipfile.ZipFile(a.assets) as z:
   assert set(z.namelist())=={r['path'] for r in lock['files']}
   for row in lock['files']:
    raw=z.read(row['path']);assert len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'];(root/row['path']).write_bytes(raw)
  compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  sources=['Program.cs','AutoUpdate.cs','Diagnostics.cs','LauncherBootstrapDiagnostics.cs','MotionControls.cs','MainDesign.cs','RegisterDesign.cs','DesignProof.cs','ComponentRuntime.cs']
  refs=['System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll']
  args=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(a.output.resolve()),'/win32icon:'+str(root/'launcher.ico'),'/win32manifest:'+str(HERE/'app.manifest'),'/resource:'+str(HERE/'runtime-files.signed.json')+',ElsFriends.RuntimeFiles','/resource:'+str(root/'ruben.png')+',ElsFriends.Ruben',*['/reference:'+r for r in refs],*[str(HERE/s) for s in sources]]
  subprocess.run(args,check=True)
 print(json.dumps(dict(ok=True,path=str(a.output.resolve()),sha256=digest(a.output),size=a.output.stat().st_size,runtime_ZIP_not_embedded=True,server_deployed=False)))
if __name__=='__main__':main()
