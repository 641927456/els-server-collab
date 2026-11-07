"""Build a private launcher candidate from the actual installed parent.

No publication, database, service or current-pointer mutations.
"""
from pathlib import Path
import base64,copy,hashlib,json,os,re,shutil,subprocess,sys,zipfile
R=Path('G:/els');H=Path(__file__).resolve().parent;D=H/'candidate-r2'
sys.path.insert(0,str(R/'tools/pylibs'))
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
read=lambda p:json.loads(Path(p).read_bytes())
def sha(p):
 with Path(p).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(p,v):Path(p).write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
def replace(path,before,after):
 text=path.read_text('utf8');assert text.count(before)==1,before[:100];path.write_text(text.replace(before,after),'utf8')
parent=read(R/'releases/launchers/current.json');base=Path(parent['update_source']).parent;old=read(base/'build.json')
assert sha(parent['path'])==parent['sha256']==old['exe_sha256']
assert not D.exists();D.mkdir();source=D/'source';shutil.copytree(base/'source',source)
key=serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA'])/'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(),None)
binding=old['signed_bindings']['signedFriends'];archive=Path(binding['archive']['path']);assert sha(archive)==binding['archive']['sha256']
wrapped=read(binding['manifest']['path']);payload=base64.b64decode(wrapped['payload']);key.public_key().verify(base64.b64decode(wrapped['signature']),payload,padding.PKCS1v15(),hashes.SHA256())
definition=json.loads(payload);files=definition['files'];assert len(files)==2786
assert not any(r['path'].startswith('state/')for r in files)
assets=D/'assets';assets.mkdir();chunks=[];groups=[];group=[];size=0
for row in sorted(files,key=lambda r:r['path']):
 if group and(len(group)>=64 or size+row['size']>32*1024**2):groups.append(group);group=[];size=0
 group.append(row);size+=row['size']
if group:groups.append(group)
with zipfile.ZipFile(archive)as full:
 assert set(full.namelist())=={r['path']for r in files}
 for group in groups:
  temporary=assets/'building.zip'
  with zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as bundle:
   for row in group:
    data=full.read(row['path']);assert len(data)==row['size']and hashlib.sha256(data).hexdigest()==row['sha256']
    info=zipfile.ZipInfo(row['path'],(2026,11,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;bundle.writestr(info,data)
  digest=sha(temporary);name='chunk-'+digest+'.zip';temporary.rename(assets/name)
  chunks.append(dict(file=name,size=(assets/name).stat().st_size,sha256=digest,files=[r['path']for r in group]))
definition['chunks']=chunks;definition['distribution']='github-releases-v1'
save(D/'runtime-files.json',definition)
payload=json.dumps(definition,separators=(',',':')).encode();signed=json.dumps(dict(payload=base64.b64encode(payload).decode(),signature=base64.b64encode(key.sign(payload,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode()
envelope=D/'signedFriends.signed.json';envelope.write_bytes(signed);(source/'resources/ui-scroll-signedFriends.signed.json').write_bytes(signed)
replace(source/'UIScrollRuntimeCohort.cs','FriendsEnvelope="'+sha(binding['manifest']['path'])+'"','FriendsEnvelope="'+sha(envelope)+'"')
version=parent['V']+1;replace(source/'AutoUpdate.cs','public const int Version = '+str(parent['V'])+';','public const int Version = '+str(version)+';')
replace(source/'AutoUpdate.cs','public const string BaseUrl = "https://134.175.57.52:19411/launcher-updates/";','public const string BaseUrl = GitHubUpdates.Root;')
text=(source/'AutoUpdate.cs').read_text('utf8');start=text.index('        internal static HttpWebResponse Open(string name) {');end=text.index('        public static LauncherRelease Latest()',start)
text=text[:start]+'        internal static HttpWebResponse Open(string name) {return GitHubUpdates.Open(name);}\n'+text[end:]
text=re.sub(r'^        public const string CertificatePin = "[a-f0-9]{64}";\n','',text,flags=re.M)
(source/'AutoUpdate.cs').write_text(text,'utf8');shutil.copyfile(H/'GitHubUpdates.cs',source/'GitHubUpdates.cs')
replace(source/'ComponentRuntime.cs','sealed class RuntimeDefinition {public string Identity,Hash,Archive;public long Size;public List<RuntimeFile> Files;}', 'sealed class RuntimeChunk {public string File,Hash;public long Size;public List<string> Files;}\n    sealed class RuntimeDefinition {public string Identity,Hash,Archive;public long Size;public List<RuntimeFile> Files;public List<RuntimeChunk> Chunks=new List<RuntimeChunk>();}')
replace(source/'ComponentRuntime.cs','Production always uses the pinned, fixed update endpoint.','Production uses the public GitHub release transport.')
replace(source/'ComponentRuntime.cs','static Stream Open(string name) {if(TestTransport!=null)return TestTransport(name);return AutoUpdate.Open(name).GetResponseStream();}','static Stream Open(string name,string runtimeHash=null) {if(TestTransport!=null)return TestTransport(name);return GitHubUpdates.Open(name,runtimeHash).GetResponseStream();}')
replace(source/'ComponentRuntime.cs','Action<string> progress,string label) {','Action<string> progress,string label,string runtimeHash=null) {')
replace(source/'ComponentRuntime.cs','using(var input=Open(name))CopyChecked','using(var input=Open(name,runtimeHash))CopyChecked')
replace(source/'ComponentRuntime.cs','if(def.Files.Count==0||!names.Contains("python/python.exe"))throw new IOException("Missing runtime entry point");return def;', '''if(def.Files.Count==0||!names.Contains("python/python.exe"))throw new IOException("Missing runtime entry point");
            object chunkRows;
            if(doc.TryGetValue("chunks",out chunkRows)) {
                var remaining=new HashSet<string>(def.Files.Select(f=>f.Path),StringComparer.Ordinal);var assets=new HashSet<string>(StringComparer.Ordinal);
                foreach(Dictionary<string,object> row in (IEnumerable)chunkRows) {
                    var chunk=new RuntimeChunk {File=(string)row["file"],Hash=(string)row["sha256"],Size=Convert.ToInt64(row["size"]),Files=new List<string>()};
                    if(!HashText(chunk.Hash)||chunk.File!="chunk-"+chunk.Hash+".zip"||chunk.Size<1||chunk.Size>536870912||!assets.Add(chunk.File)||def.Chunks.Count>=4096)throw new IOException("Invalid runtime chunk");
                    foreach(string path in (IEnumerable)row["files"]) {if(!remaining.Remove(path)||chunk.Files.Count>=64)throw new IOException("Invalid chunk member");chunk.Files.Add(path);}
                    if(chunk.Files.Count==0)throw new IOException("Empty runtime chunk");def.Chunks.Add(chunk);
                }
                if(remaining.Count!=0)throw new IOException("Incomplete runtime chunk index");
            }
            return def;''')
replace(source/'ComponentRuntime.cs','if(!cached&&(reused==0||missing.Count>=64)) {','if(!cached&&missing.Count>0&&(reused==0||missing.Count>=64||def.Chunks.Count==0)) {')
replace(source/'ComponentRuntime.cs','''}else foreach(var row in missing) {
                    DownloadChecked("blob-"+row.Hash+".bin",Under(stage,row.Path),row.Size,row.Hash,progress,"更新运行组件 "+(downloaded+1)+" / "+missing.Count);downloaded++;bytes+=row.Size;
                }''','''}else foreach(var chunk in def.Chunks) {
                    var selected=missing.Where(r=>chunk.Files.Contains(r.Path)).ToList();if(selected.Count==0)continue;
                    string package=Under(packages,chunk.File);
                    if(!Regular(package,packages)||new FileInfo(package).Length!=chunk.Size||Digest(package)!=chunk.Hash) {
                        string temporary=package+"."+Guid.NewGuid().ToString("N")+".part";
                        try {
                            DownloadChecked(chunk.File,temporary,chunk.Size,chunk.Hash,progress,"更新运行组件",def.Hash);bytes+=chunk.Size;
                            if(File.Exists(package))File.Replace(temporary,package,null);else File.Move(temporary,package);
                        }finally{if(File.Exists(temporary))File.Delete(temporary);}
                    }
                    using(var zip=ZipFile.OpenRead(package)) {
                        var expected=new HashSet<string>(chunk.Files,StringComparer.Ordinal);var seen=new HashSet<string>(StringComparer.Ordinal);
                        foreach(var entry in zip.Entries){SafeRelative(entry.FullName);if(!expected.Contains(entry.FullName)||!seen.Add(entry.FullName))throw new IOException("Unexpected chunk member");}
                        if(seen.Count!=expected.Count)throw new IOException("Missing chunk member");
                        foreach(var row in selected){var entry=zip.GetEntry(row.Path);if(entry.Length!=row.Size)throw new IOException("Chunk member size differs");using(var input=entry.Open())CopyChecked(input,Under(stage,row.Path),row.Size,row.Hash);downloaded++;}
                    }
                }''')
resources=copy.deepcopy(old['resources'])
for row in resources:
 if row['name']=='ElsFriends.UIScrollFriendsRuntimeFiles':row['sha256']=sha(envelope)
 assert sha(source/row['path'])==row['sha256'],row['path']
exe=D/('ElsFriends-V'+str(version)+'.exe');compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
command=[str(compiler),'/nologo','/target:winexe','/optimize+','/platform:x64','/codepage:65001','/out:'+str(exe),'/win32icon:'+str(R/'launcher/assets/launcher.ico'),'/win32manifest:'+str(source/'app.manifest')]
command+=['/resource:'+str(source/r['path'])+','+r['name']for r in resources]
command+=['/reference:'+n for n in('System.Windows.Forms.dll','System.Drawing.dll','System.Web.Extensions.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','System.Security.dll')]
command+=[str(p)for p in sorted(source.glob('*.cs'))]
result=subprocess.run(command,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=90);(D/'compile.txt').write_bytes(result.stdout+result.stderr);assert result.returncode==0,result.stdout.decode('utf8','replace')[-1800:]
inventory={p.relative_to(source).as_posix():dict(size=p.stat().st_size,sha256=sha(p))for p in source.rglob('*')if p.is_file()}
out=dict(ok=True,private_candidate=True,published=False,qualification_complete=False,version=version,exe=str(exe),exe_sha256=sha(exe),size=exe.stat().st_size,parent=parent,resources=resources,source_inventory=inventory,source_changes=[n for n,v in inventory.items()if v!=old['source_inventory'].get(n)],payload_files=len(files),original_EXE_KOM_changes=0,engine_unchanged=True,chunk_count=len(chunks))
out['signed_bindings']=copy.deepcopy(old['signed_bindings']);out['signed_bindings']['signedFriends']=dict(manifest=dict(path=str(envelope),sha256=sha(envelope),size=envelope.stat().st_size),archive=binding['archive'])
save(D/'build.json',out)
release=dict(schema=1,product='ElsFriends',channel='friends',version=version,size=out['size'],sha256=out['exe_sha256'],file='v'+str(version)+'-'+out['exe_sha256'][:16]+'.exe')
payload=json.dumps(release,separators=(',',':')).encode();save(D/'latest.json',dict(payload=base64.b64encode(payload).decode(),signature=base64.b64encode(key.sign(payload,padding.PKCS1v15(),hashes.SHA256())).decode()))
assert read(R/'releases/launchers/current.json')==parent
print(json.dumps(dict(version=version,exe_sha256=out['exe_sha256'],source_changes=out['source_changes'],runtime_unchanged=True,chunks=len(chunks))))
