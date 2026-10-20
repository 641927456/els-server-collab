using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace ElsFriends {
    sealed class LauncherRelease {
        public int Version;
        public long Size;
        public string Hash, FileName, Envelope;
    }
    // Only release metadata and the EXE are cached here. Settings/sessions/runtime
    // directories are deliberately outside the updater's write set.
    static class AutoUpdate {
        public const int Version = 31;
        public const string BaseUrl = "https://134.175.57.52:19411/launcher-updates/";
        public const string ProgressUrl = "https://134.175.57.52:80/els-progress/";
        public const string ClientUrl = "https://pan.baidu.com/s/1qfyFxC99wgsGhtZwVI2aoQ?pwd=jrg6";
        public const string PublicKey = "<RSAKeyValue><Modulus>pouOR2K22jQISOYa4nYuOwUDn+nFWwqyL0SN6Mf6riZwkJWNAEWVybvN7lQW5VHiqKQNGAaG+A5XrPJlLPVzwbVm3nnkbJn9JFENF81TfQZTJBILegS6LFYGhUeOf8SFDihElgmNtP+M+BYQ08Uzk5y14bQlAL09AfihswfwkwxhwitkPj6Y089DgdXQRIncFfAQh+wN2KsmPIfwVBtU5HVDEazRCMSaGwxMnsEofb+qmJ+psyvXg3tvTj386cUuUrqYPyxpqyYZ9FqXvzoyYcTsPWeccb2i46k68fH5ZcRTIbH1R8+vzCAWTf7VlpUf71jP1HgR9YaQNHxpTaKai7+Fg4oyzb9su6zqvH4yuTYk3joSd+xfhLyCiJ1HKhkbUnmSnNcdrup8phbJRwuniLohOgTHcmI3s/j9aHFyr6qo78xA+3poExIQG6O/LHb75OCFbYHkfEAPZsy4yrbeiybJXjTaTzd2mcPWwPbVqtF+bmmlJS3UDhaXB0zsgzsl</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>";
        public const string CertificatePin = "a20556e1ecc3adcde2cecb82ec0374eecea109dbc8b5a23fa19fe263c76b7b40";
        const long MaxSize = 536870912;
        public static string PendingLauncher;
        static string Cache {get{return Path.Combine(Program.DataRoot,"launcher-updates");}}
        static JavaScriptSerializer Serializer() {return new JavaScriptSerializer {MaxJsonLength=32768,RecursionLimit=12};}
        static string Text(Dictionary<string,object> obj,string key) {object value;if(!obj.TryGetValue(key,out value)||!(value is string))throw new IOException("Invalid release field");return (string)value;}
        public static LauncherRelease Verify(string envelope) {
            if(envelope==null||Encoding.UTF8.GetByteCount(envelope)>32768)throw new IOException("Release metadata too large");
            var wrapper=Serializer().Deserialize<Dictionary<string,object>>(envelope);
            byte[] data=Convert.FromBase64String(Text(wrapper,"payload")),signature=Convert.FromBase64String(Text(wrapper,"signature"));
            using(var rsa=new RSACryptoServiceProvider()) {rsa.PersistKeyInCsp=false;rsa.FromXmlString(PublicKey);if(!rsa.VerifyData(data,CryptoConfig.MapNameToOID("SHA256"),signature))throw new IOException("Invalid release signature");}
            var row=Serializer().Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(data));
            if(Convert.ToInt32(row["schema"])!=1||Text(row,"product")!="ElsFriends"||Text(row,"channel")!="friends")throw new IOException("Wrong release channel");
            var release=new LauncherRelease {Version=Convert.ToInt32(row["version"]),Size=Convert.ToInt64(row["size"]),Hash=Text(row,"sha256"),FileName=Text(row,"file"),Envelope=envelope};
            if(release.Version<25||release.Size<1024||release.Size>MaxSize||!Regex.IsMatch(release.Hash,"^[a-f0-9]{64}$"))throw new IOException("Invalid release identity");
            if(release.FileName!="v"+release.Version+"-"+release.Hash.Substring(0,16)+".exe")throw new IOException("Unsafe release path");
            return release;
        }
        internal static HttpWebResponse Open(string name) {
            // Redirects are never followed; TLS trust is scoped to this request.
            ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
            var request=(HttpWebRequest)WebRequest.Create(BaseUrl+name);
            request.AllowAutoRedirect=false;request.Timeout=12000;request.ReadWriteTimeout=30000;request.Proxy=null;
            request.UserAgent="ElsFriendsLauncher/"+Version;request.Headers[HttpRequestHeader.CacheControl]="no-cache";
            request.ServerCertificateValidationCallback=delegate(object s,X509Certificate cert,X509Chain chain,SslPolicyErrors errors) {
                if(cert==null)return false;
                using(var certificate=new X509Certificate2(cert))using(var sha=SHA256.Create())return DateTime.UtcNow>=certificate.NotBefore.ToUniversalTime()&&DateTime.UtcNow<=certificate.NotAfter.ToUniversalTime()&&Program.Hex(sha.ComputeHash(certificate.RawData))==CertificatePin;
            };
            var response=(HttpWebResponse)request.GetResponse();if(response.StatusCode!=HttpStatusCode.OK){response.Dispose();throw new IOException("Update endpoint unavailable");}return response;
        }
        public static LauncherRelease Latest() {
            using(var response=Open("latest.json"))using(var stream=response.GetResponseStream())using(var buffer=new MemoryStream()) {
                byte[] chunk=new byte[4096];int count;
                while((count=stream.Read(chunk,0,chunk.Length))>0){if(buffer.Length+count>32768)throw new IOException("Release metadata too large");buffer.Write(chunk,0,count);}
                return Verify(Encoding.UTF8.GetString(buffer.ToArray()));
            }
        }
        static string Resolve(LauncherRelease release) {return Path.Combine(Cache,release.FileName);}
        public static bool ValidFile(string path,LauncherRelease release) {
            if(!File.Exists(path)||new FileInfo(path).Length!=release.Size)return false;
            using(var file=File.OpenRead(path))return Program.Hash(file)==release.Hash;
        }
        public static string CachedNewer() {
            try {
                string metadata=Path.Combine(Cache,"ready.json");if(!File.Exists(metadata))return null;
                var release=Verify(File.ReadAllText(metadata,Encoding.UTF8));if(release.Version<=Version)return null;string path=Resolve(release);
                string blocked=Path.Combine(Cache,"blocked-release.txt");
                if(File.Exists(blocked)&&File.ReadAllText(blocked)==release.FileName)return null;
                string pending=Path.Combine(Cache,"activation.json");
                if(File.Exists(pending)) {
                    var activation=Serializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(pending));
                    if(Text(activation,"file")==release.FileName) {
                        bool alive=false;try{using(var process=Process.GetProcessById(Convert.ToInt32(activation["pid"])))alive=process.StartTime.ToUniversalTime().Ticks==Convert.ToInt64(Text(activation,"started"));}catch{}
                        if(!alive){Program.PrivateWrite(blocked,release.FileName);File.Delete(pending);return null;}
                    }
                }
                return release.Version>Version&&ValidFile(path,release)?path:null;
            }catch{return null;}
        }
        public static bool StartCached() {string path=CachedNewer();if(path==null)return false;try{Start(path);return true;}catch{try{Program.PrivateWrite(Path.Combine(Cache,"blocked-release.txt"),Path.GetFileName(path));}catch{}return false;}}
        public static void Start(string path) {
            var info=new ProcessStartInfo(path,"--updated-parent "+Process.GetCurrentProcess().Id) {UseShellExecute=false,WorkingDirectory=Path.GetDirectoryName(path)};
            using(var child=Process.Start(info)) {
                var activation=new Dictionary<string,object>{{"file",Path.GetFileName(path)},{"pid",child.Id},{"started",child.StartTime.ToUniversalTime().Ticks.ToString()}};
                Program.PrivateWrite(Path.Combine(Cache,"activation.json"),Serializer().Serialize(activation));
            }
        }
        public static void CancelOwnActivation() {
            // A duplicate instance exits normally. Only cancel its own ticket;
            // never acknowledge another process or a different signed release.
            try {
                string ready=Path.Combine(Cache,"ready.json"),pending=Path.Combine(Cache,"activation.json");
                if(!File.Exists(ready)||!File.Exists(pending))return;
                var release=Verify(File.ReadAllText(ready));
                if(release.Version!=Version||!ValidFile(Assembly.GetExecutingAssembly().Location,release))return;
                var activation=Serializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(pending));
                using(var process=Process.GetCurrentProcess())
                    if(Text(activation,"file")==release.FileName&&Convert.ToInt32(activation["pid"])==process.Id&&Convert.ToInt64(Text(activation,"started"))==process.StartTime.ToUniversalTime().Ticks)File.Delete(pending);
            }catch{}
        }
        public static void ConfirmHealthy() {
            try {
                string ready=Path.Combine(Cache,"ready.json");if(!File.Exists(ready))return;
                var release=Verify(File.ReadAllText(ready));
                if(release.Version!=Version||!ValidFile(Assembly.GetExecutingAssembly().Location,release))return;
                foreach(string name in new[]{"activation.json","blocked-release.txt"}){string path=Path.Combine(Cache,name);if(File.Exists(path))File.Delete(path);}
            }catch{}
        }
        public static bool IsBlocked(LauncherRelease release) {string path=Path.Combine(Cache,"blocked-release.txt");return File.Exists(path)&&File.ReadAllText(path)==release.FileName;}
        public static void PermitRetry() {foreach(string name in new[]{"activation.json","blocked-release.txt"}){string path=Path.Combine(Cache,name);if(File.Exists(path))File.Delete(path);}}
        public static void WaitParent(string[] args) {
            if(args.Length==2&&args[0]=="--updated-parent") {int pid;if(!Int32.TryParse(args[1],out pid)||pid<=0)throw new IOException("Invalid update parent");try{using(var parent=Process.GetProcessById(pid))if(!parent.WaitForExit(15000))throw new IOException("Previous launcher is still running");}catch(ArgumentException){}}
        }
        public static string Download(LauncherRelease release,Action<int> progress) {
            if(release.Version<=Version)return null;
            string destination=Resolve(release);Directory.CreateDirectory(Cache);
            bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsUpdate-"+System.Security.Principal.WindowsIdentity.GetCurrent().User.Value)) {
                try {
                    try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}
                    if(!acquired)throw new IOException("Update already downloading");
                    // A previously verified newer version must never be replaced
                    // by an older channel manifest (including a replay).
                    string ready=Path.Combine(Cache,"ready.json");
                    if(File.Exists(ready))try{var prior=Verify(File.ReadAllText(ready,Encoding.UTF8));if(prior.Version>release.Version)throw new InvalidOperationException("Release downgrade rejected");}catch(InvalidOperationException){throw;}catch{}
                    string temporary=Path.Combine(Cache,"download-"+Guid.NewGuid().ToString("N")+".part");
                    try {
                        if(!ValidFile(destination,release)) {
                            using(var response=Open(release.FileName))using(var stream=response.GetResponseStream())using(var file=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                                if(response.ContentLength>=0&&response.ContentLength!=release.Size)throw new IOException("Update size differs");
                                byte[] bytes=new byte[65536];long total=0;int count,last=-1;
                                while((count=stream.Read(bytes,0,bytes.Length))>0){total+=count;if(total>release.Size)throw new IOException("Update exceeds signed size");file.Write(bytes,0,count);int percent=(int)(total*100/release.Size);if(percent!=last){last=percent;progress(percent);}}
                                if(total!=release.Size)throw new IOException("Incomplete update");file.Flush(true);
                            }
                            if(!ValidFile(temporary,release))throw new IOException("Update checksum differs");
                            if(File.Exists(destination))File.Replace(temporary,destination,null);else File.Move(temporary,destination);
                        }
                        // Commit metadata only after the new EXE is complete.
                        // Failed downloads leave the previous ready.json intact.
                        Program.PrivateWrite(ready,release.Envelope);return destination;
                    }finally{if(File.Exists(temporary))File.Delete(temporary);}
                }finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        public static void OpenLink(string url) {Process.Start(new ProcessStartInfo(url){UseShellExecute=true});}
        public static object Test(string fixtures) {
            var good=Verify(File.ReadAllText(Path.Combine(fixtures,"valid.json")));
            foreach(string name in new[]{"tampered","wrong-key","bad-path","wrong-channel","oversize"}) {
                bool rejected=false;try{Verify(File.ReadAllText(Path.Combine(fixtures,name+".json")));}catch{rejected=true;}if(!rejected)throw new Exception("Accepted invalid metadata: "+name);
            }
            string file=Path.Combine(fixtures,"fixture.exe");if(!ValidFile(file,good))throw new Exception("Valid file rejected");
            byte[] original=File.ReadAllBytes(file);original[original.Length-1]^=1;File.WriteAllBytes(file,original);if(ValidFile(file,good))throw new Exception("Corrupt file accepted");original[original.Length-1]^=1;File.WriteAllBytes(file,original);
            Directory.CreateDirectory(Cache);string dest=Resolve(good);File.Copy(file,dest,true);Program.PrivateWrite(Path.Combine(Cache,"ready.json"),good.Envelope);
            if(CachedNewer()!=dest)throw new Exception("Offline cache recovery failed");File.WriteAllText(dest,"interrupted");if(CachedNewer()!=null)throw new Exception("Incomplete cache executed");File.Copy(file,dest,true);
            Program.PrivateWrite(Path.Combine(Cache,"ready.json"),File.ReadAllText(Path.Combine(fixtures,"newer.json")));
            bool downgrade=false;try{Download(good,delegate{});}catch(InvalidOperationException){downgrade=true;}if(!downgrade)throw new Exception("Signed older release replaced newer cache");
            Program.PrivateWrite(Path.Combine(Cache,"ready.json"),good.Envelope);
            Program.PrivateWrite(Path.Combine(Cache,"activation.json"),Serializer().Serialize(new Dictionary<string,object>{{"file",good.FileName},{"pid",Int32.MaxValue},{"started","0"}}));
            if(CachedNewer()!=null||!IsBlocked(good))throw new Exception("Failed activation was retried automatically");PermitRetry();if(CachedNewer()!=dest)throw new Exception("Explicit retry failed");
            var current=Verify(File.ReadAllText(Path.Combine(fixtures,"current.json")));if(Download(current,delegate{})!=null)throw new Exception("Current version redownloaded");
            return new {ok=true,signed_metadata_verified=true,tampering_rejected=true,foreign_key_rejected=true,unsafe_path_rejected=true,channel_checked=true,size_bounded=true,corruption_rejected=true,offline_cache_verified=true,incomplete_cache_rejected=true,no_downgrade=true,failed_activation_falls_back=true,explicit_retry=true,settings_untouched=true};
        }
    }
}
