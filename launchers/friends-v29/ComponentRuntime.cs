using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace ElsFriends {
    sealed class RuntimeFile {public string Path,Hash;public long Size;}
    sealed class RuntimeDefinition {public string Identity,Hash,Archive;public long Size;public List<RuntimeFile> Files;}
    static class ComponentRuntime {
        public static object LastResult;
        public static string PreparedRoot;
        // Test transport is available only through reflection in an isolated
        // process. Production always uses the pinned, fixed update endpoint.
        internal static Func<string,Stream> TestTransport;
        internal static string TestManifest;
        static Stream Open(string name) {if(TestTransport!=null)return TestTransport(name);return AutoUpdate.Open(name).GetResponseStream();}
        static string Digest(string path) {using(var f=File.OpenRead(path))return Program.Hash(f);}
        static bool HashText(string text) {return Regex.IsMatch(text??"","^[a-f0-9]{64}$");}
        static void SafeRelative(string path) {
            if(String.IsNullOrEmpty(path)||path.Length>220||path.Contains('\\')||path.Contains(':')||path.StartsWith("/")||path.IndexOfAny(new[]{'\0','\r','\n','*','?','"','<','>','|'})>=0)throw new IOException("Unsafe component path");
            foreach(string part in path.Split('/'))if(part.Length==0||part=="."||part==".."||part.EndsWith(".")||part.EndsWith(" ")||Regex.IsMatch(part,"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\\.|$)",RegexOptions.IgnoreCase))throw new IOException("Unsafe component leaf");
        }
        internal static RuntimeDefinition Verify(string envelope) {
            var json=new JavaScriptSerializer {MaxJsonLength=4*1024*1024,RecursionLimit=16};
            if(envelope.Length>4*1024*1024)throw new IOException("Component manifest too large");
            var wrapper=json.Deserialize<Dictionary<string,object>>(envelope);byte[] data=Convert.FromBase64String((string)wrapper["payload"]),signature=Convert.FromBase64String((string)wrapper["signature"]);
            using(var rsa=new RSACryptoServiceProvider()){rsa.PersistKeyInCsp=false;rsa.FromXmlString(AutoUpdate.PublicKey);if(!rsa.VerifyData(data,CryptoConfig.MapNameToOID("SHA256"),signature))throw new IOException("Invalid component signature");}
            var doc=json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(data));
            if(Convert.ToInt32(doc["schema"])!=1||(string)doc["product"]!="ElsFriends"||(string)doc["channel"]!="friends"||(string)doc["kind"]!="runtime-files")throw new IOException("Wrong component channel");
            var archive=(Dictionary<string,object>)doc["archive"];var def=new RuntimeDefinition {Hash=(string)archive["sha256"],Archive=(string)archive["file"],Size=Convert.ToInt64(archive["size"]),Files=new List<RuntimeFile>()};
            using(var m=new MemoryStream(data))def.Identity=Program.Hash(m);
            if(!HashText(def.Hash)||def.Archive!="runtime-"+def.Hash+".zip"||def.Size<1024||def.Size>536870912)throw new IOException("Invalid runtime archive");
            var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long total=0;
            foreach(Dictionary<string,object> row in (IEnumerable)doc["files"]) {
                var file=new RuntimeFile {Path=(string)row["path"],Hash=(string)row["sha256"],Size=Convert.ToInt64(row["size"])};SafeRelative(file.Path);if(file.Path.Equals(".complete",StringComparison.OrdinalIgnoreCase))throw new IOException("Reserved runtime marker");
                if(!names.Add(file.Path)||!HashText(file.Hash)||file.Size<0||file.Size>268435456)throw new IOException("Invalid component entry");
                total+=file.Size;if(total>2147483648L||def.Files.Count>=4096)throw new IOException("Runtime size budget");def.Files.Add(file);
            }
            if(def.Files.Count==0||!names.Contains("python/python.exe"))throw new IOException("Missing runtime entry point");return def;
        }
        static RuntimeDefinition Definition() {
            string text=TestManifest;
            if(text==null)using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends.RuntimeFiles"))using(var reader=new StreamReader(stream,Encoding.UTF8))text=reader.ReadToEnd();
            var def=Verify(text);if(TestManifest==null&&def.Hash!=Program.PayloadHash)throw new IOException("Runtime binding differs");return def;
        }
        static string Under(string root,string relative) {SafeRelative(relative);string path=System.IO.Path.GetFullPath(System.IO.Path.Combine(root,relative.Replace('/',System.IO.Path.DirectorySeparatorChar)));if(!path.StartsWith(System.IO.Path.GetFullPath(root)+System.IO.Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Runtime path escaped");return path;}
        static bool Regular(string path,string root) {
            try {
                if(!File.Exists(path))return false;
                for(string p=path;p!=null;p=System.IO.Path.GetDirectoryName(p)) {
                    if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)return false;
                    if(String.Equals(p,System.IO.Path.GetFullPath(root),StringComparison.OrdinalIgnoreCase))return true;
                }
            }catch{}return false;
        }
        static bool Valid(string root,RuntimeFile row) {try{string p=Under(root,row.Path);return Regular(p,root)&&new FileInfo(p).Length==row.Size&&Digest(p)==row.Hash;}catch{return false;}}
        static bool Complete(string root,RuntimeDefinition def) {return Directory.Exists(root)&&def.Files.All(row=>Valid(root,row));}
        static void CopyChecked(Stream source,string destination,long size,string hash) {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(destination));
            using(var target=new FileStream(destination,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                byte[] buffer=new byte[65536];long total=0;int count;
                while((count=source.Read(buffer,0,buffer.Length))>0){total+=count;if(total>size)throw new IOException("Component exceeds signed size");target.Write(buffer,0,count);}
                if(total!=size)throw new IOException("Truncated component");target.Flush(true);
            }
            if(Digest(destination)!=hash)throw new IOException("Component checksum differs");
        }
        static void CleanupOwnStage(string stage,string root) {
            if(!System.IO.Path.GetFullPath(stage).StartsWith(System.IO.Path.GetFullPath(root)+System.IO.Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||!System.IO.Path.GetFileName(stage).StartsWith("prepare-"))throw new IOException("Unsafe stage cleanup");
            if(Directory.Exists(stage)) {
                // No recursive traversal through a link, including directories.
                var pending=new Stack<string>();pending.Push(stage);
                while(pending.Count>0)foreach(string p in Directory.GetFileSystemEntries(pending.Pop())) {if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked stage");if(Directory.Exists(p))pending.Push(p);}
                Directory.Delete(stage,true);
            }
        }
        static List<string> Sources(string components) {
            var result=new List<string>();foreach(string root in new[]{System.IO.Path.Combine(Program.DataRoot,"versions"),components})if(Directory.Exists(root)) {
                if((File.GetAttributes(root)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked component root");
                foreach(string path in Directory.GetDirectories(root).OrderByDescending(p=>Directory.GetLastWriteTimeUtc(p)).Take(32))
                    if(!System.IO.Path.GetFileName(path).StartsWith("prepare-")&&(File.GetAttributes(path)&FileAttributes.ReparsePoint)==0)result.Add(path);
            }return result;
        }
        static bool LegacyArchive(string destination,RuntimeDefinition def) {
            // Loading resources is restricted to these immutable, previously
            // accepted full launchers. No arbitrary neighboring EXE is loaded.
            var known=new Dictionary<string,string>{{"艾尔之光朋友服-V28-焕新界面.exe","c31a47def2c16e026f0c379ed936daba9fcaa2dd03203118d2c3a00fdc83862a"},{"艾尔之光朋友服-V27-焕新界面.exe","5edf8ed84083e17a374944a3c6e34cf7e17dc3d37a784a23f6edeb25da26676e"},{"艾尔之光朋友服-V26-焕新界面.exe","cd9864f9ef5ad1dd069daa95e224e82842cc390af6068c4dd895e12128c77b18"}};
            var candidates=new Dictionary<string,string>();foreach(var row in known) {
                candidates[System.IO.Path.Combine(AppDomain.CurrentDomain.BaseDirectory,row.Key)]=row.Value;
                int v=row.Key.Contains("V28")?28:row.Key.Contains("V27")?27:26;candidates[System.IO.Path.Combine(Program.DataRoot,"launcher-updates","v"+v+"-"+row.Value.Substring(0,16)+".exe")]=row.Value;
            }
            foreach(var row in candidates)try {
                if(!File.Exists(row.Key)||Digest(row.Key)!=row.Value)continue;
                using(var stream=Assembly.LoadFile(System.IO.Path.GetFullPath(row.Key)).GetManifestResourceStream("ElsFriends.Payload")) {if(stream==null)continue;CopyChecked(stream,destination,def.Size,def.Hash);return true;}
            }catch{if(File.Exists(destination))File.Delete(destination);}return false;
        }
        public static string Ensure(Action<string> progress) {
            bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}if(!acquired)throw new IOException("Runtime preparation already active");return Prepare(Definition(),progress);}
                finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        static string Prepare(RuntimeDefinition def,Action<string> progress) {
            string components=System.IO.Path.GetFullPath(System.IO.Path.Combine(Program.DataRoot,"component-runtimes"));Directory.CreateDirectory(components);
            if((File.GetAttributes(components)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked component directory");
            string target=Under(components,def.Hash.Substring(0,16)+"-"+def.Identity.Substring(0,12));var sources=Sources(components);
            progress("正在校验运行环境，未变化的文件将直接复用…");
            foreach(string source in new[]{target}.Concat(sources).Distinct(StringComparer.OrdinalIgnoreCase))if(Complete(source,def)) {
                CommitPointer(source,def);LastResult=new {reused_files=def.Files.Count,downloaded_files=0,downloaded_bytes=0L,full_archive_downloaded=false,existing_environment_reused=true};return source;
            }
            string stage=System.IO.Path.Combine(components,"prepare-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
            int reused=0,downloaded=0;long bytes=0;bool full=false,legacy=false;var missing=new List<RuntimeFile>();
            try {
                foreach(var row in def.Files) {
                    string source=sources.FirstOrDefault(p=>Valid(p,row));
                    if(source==null){missing.Add(row);continue;}
                    string dest=Under(stage,row.Path);using(var file=File.OpenRead(Under(source,row.Path)))CopyChecked(file,dest,row.Size,row.Hash);reused++;
                }
                string packages=System.IO.Path.GetFullPath(System.IO.Path.Combine(Program.DataRoot,"component-packages"));Directory.CreateDirectory(packages);
                if((File.GetAttributes(packages)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked package directory");
                string archive=Under(packages,def.Archive);bool cached=Regular(archive,packages)&&new FileInfo(archive).Length==def.Size&&Digest(archive)==def.Hash;
                if(!cached&&reused==0) {
                    string temporary=archive+"."+Guid.NewGuid().ToString("N")+".part";
                    try {
                        legacy=LegacyArchive(temporary,def);
                        if(!legacy){progress("首次使用，正在下载运行环境…");using(var input=Open(def.Archive))CopyChecked(input,temporary,def.Size,def.Hash);bytes+=def.Size;full=true;}
                        if(File.Exists(archive))File.Replace(temporary,archive,null);else File.Move(temporary,archive);cached=true;
                    }finally{if(File.Exists(temporary))File.Delete(temporary);}
                }
                if(cached) {
                    using(var zip=ZipFile.OpenRead(archive)) {
                        var expected=new HashSet<string>(def.Files.Select(r=>r.Path),StringComparer.Ordinal);var seen=new HashSet<string>(StringComparer.Ordinal);
                        foreach(var entry in zip.Entries){if(entry.FullName.EndsWith("/"))continue;SafeRelative(entry.FullName);if(!expected.Contains(entry.FullName)||!seen.Add(entry.FullName))throw new IOException("Unexpected runtime member");}
                        if(seen.Count!=expected.Count)throw new IOException("Missing runtime member");
                        foreach(var row in missing){var entry=zip.GetEntry(row.Path);if(entry.Length!=row.Size)throw new IOException("Runtime member size differs");using(var input=entry.Open())CopyChecked(input,Under(stage,row.Path),row.Size,row.Hash);}
                    }
                }else foreach(var row in missing) {
                    progress("正在更新运行组件："+(downloaded+1)+" / "+missing.Count);
                    using(var input=Open("blob-"+row.Hash+".bin"))CopyChecked(input,Under(stage,row.Path),row.Size,row.Hash);downloaded++;bytes+=row.Size;
                }
                if(!Complete(stage,def))throw new IOException("Prepared runtime validation failed");
                File.WriteAllText(System.IO.Path.Combine(stage,".complete"),def.Hash);
                // Every old environment remains intact. A corrupt target is
                // never overwritten, since an existing game may still use it.
                if(Directory.Exists(target))target+="-repair-"+Guid.NewGuid().ToString("N").Substring(0,12);
                Directory.Move(stage,target);CommitPointer(target,def);
                LastResult=new {reused_files=reused,downloaded_files=full?missing.Count:downloaded,downloaded_bytes=bytes,full_archive_downloaded=full,legacy_archive_reused=legacy,existing_environment_reused=false};return target;
            }finally{CleanupOwnStage(stage,components);}
        }
        static void CommitPointer(string path,RuntimeDefinition def) {Program.PrivateWrite(System.IO.Path.Combine(Program.DataRoot,"component-state","current.json"),Program.Json.Serialize(new {path=path,payload_sha256=def.Hash,manifest_sha256=def.Identity}));PreparedRoot=path;}
    }
}
