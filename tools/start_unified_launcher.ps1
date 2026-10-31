param([string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot), [switch]$LibraryOnly)
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 is sufficient. The transport callback lives in C# so it
# has no PowerShell runspace dependency on the TLS worker thread.
Add-Type -ReferencedAssemblies System.Web.Extensions -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

public sealed class ElsGitRelease {
    public int Version; public long Size; public string Hash, FileName, Envelope;
}
public static class ElsGitLauncher {
    public const string BaseUrl = "https://134.175.57.52:19411/launcher-updates/";
    public const string PublicKey = "<RSAKeyValue><Modulus>pouOR2K22jQISOYa4nYuOwUDn+nFWwqyL0SN6Mf6riZwkJWNAEWVybvN7lQW5VHiqKQNGAaG+A5XrPJlLPVzwbVm3nnkbJn9JFENF81TfQZTJBILegS6LFYGhUeOf8SFDihElgmNtP+M+BYQ08Uzk5y14bQlAL09AfihswfwkwxhwitkPj6Y089DgdXQRIncFfAQh+wN2KsmPIfwVBtU5HVDEazRCMSaGwxMnsEofb+qmJ+psyvXg3tvTj386cUuUrqYPyxpqyYZ9FqXvzoyYcTsPWeccb2i46k68fH5ZcRTIbH1R8+vzCAWTf7VlpUf71jP1HgR9YaQNHxpTaKai7+Fg4oyzb9su6zqvH4yuTYk3joSd+xfhLyCiJ1HKhkbUnmSnNcdrup8phbJRwuniLohOgTHcmI3s/j9aHFyr6qo78xA+3poExIQG6O/LHb75OCFbYHkfEAPZsy4yrbeiybJXjTaTzd2mcPWwPbVqtF+bmmlJS3UDhaXB0zsgzsl</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>";
    public const string CertificatePin = "a20556e1ecc3adcde2cecb82ec0374eecea109dbc8b5a23fa19fe263c76b7b40";
    public const int MinimumVersion = 42;
    static JavaScriptSerializer Json() { return new JavaScriptSerializer { MaxJsonLength = 32768, RecursionLimit = 12 }; }
    static string Text(Dictionary<string,object> doc,string key) {
        object value; if(!doc.TryGetValue(key,out value)||!(value is string))throw new InvalidDataException("Invalid release field"); return (string)value;
    }
    static string Hex(byte[] bytes) { return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant(); }
    public static ElsGitRelease Verify(string envelope) { return VerifyWithKey(envelope,PublicKey); }
    static ElsGitRelease VerifyWithKey(string envelope,string publicKey) {
        if(envelope==null||Encoding.UTF8.GetByteCount(envelope)>32768)throw new InvalidDataException("Release metadata too large");
        var outer=Json().Deserialize<Dictionary<string,object>>(envelope);
        byte[] data=Convert.FromBase64String(Text(outer,"payload")),signature=Convert.FromBase64String(Text(outer,"signature"));
        using(var rsa=new RSACryptoServiceProvider()) {
            rsa.PersistKeyInCsp=false;rsa.FromXmlString(publicKey);
            if(!rsa.VerifyData(data,CryptoConfig.MapNameToOID("SHA256"),signature))throw new InvalidDataException("Invalid release signature");
        }
        var doc=Json().Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(data));
        if(Convert.ToInt32(doc["schema"])!=1||Text(doc,"product")!="ElsFriends"||Text(doc,"channel")!="friends")throw new InvalidDataException("Wrong release channel");
        var release=new ElsGitRelease { Version=Convert.ToInt32(doc["version"]),Size=Convert.ToInt64(doc["size"]),Hash=Text(doc,"sha256"),FileName=Text(doc,"file"),Envelope=envelope };
        if(release.Version<25||release.Size<1024||release.Size>536870912||!Regex.IsMatch(release.Hash,"^[a-f0-9]{64}$"))throw new InvalidDataException("Invalid release identity");
        if(release.FileName!="v"+release.Version+"-"+release.Hash.Substring(0,16)+".exe")throw new InvalidDataException("Unsafe release path");
        return release;
    }
    public static void RequireCurrent(ElsGitRelease release) {
        if(release.Version<MinimumVersion)throw new IOException("首次初始化需要统一启动器 V42 或更新版本，更新端点尚未提供对应版本。");
    }
    public static void RegularTree(string path) {
        string full=Path.GetFullPath(path);
        for(string item=full;item!=null;item=Path.GetDirectoryName(item))
            if((Directory.Exists(item)||File.Exists(item))&&(File.GetAttributes(item)&FileAttributes.ReparsePoint)!=0)throw new IOException("目录包含链接，请使用实际的仓库目录。");
    }
    public static string Repository(string path) {
        string root=Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
        RegularTree(root);
        if((!Directory.Exists(Path.Combine(root,".git"))&&!File.Exists(Path.Combine(root,".git")))||!File.Exists(Path.Combine(root,"els_server","application.py"))||!File.Exists(Path.Combine(root,"channels","current-engine.json")))throw new IOException("请从完整的服务端 Git 仓库根目录运行。");
        return root;
    }
    public static bool ValidFile(string path,ElsGitRelease release) {
        RegularTree(path);
        if(!File.Exists(path)||new FileInfo(path).Length!=release.Size)return false;
        using(var input=File.OpenRead(path))using(var sha=SHA256.Create())return Hex(sha.ComputeHash(input))==release.Hash;
    }
    public static bool Certificate(X509Certificate cert,DateTime now) {
        if(cert==null)return false;
        using(var certificate=new X509Certificate2(cert))using(var sha=SHA256.Create())
            return now>=certificate.NotBefore.ToUniversalTime()&&now<=certificate.NotAfter.ToUniversalTime()&&Hex(sha.ComputeHash(certificate.RawData))==CertificatePin;
    }
    static HttpWebResponse Open(string name) {
        if(name!="latest.json"&&!Regex.IsMatch(name,"^v[0-9]+-[a-f0-9]{16}\\.exe$"))throw new InvalidDataException("Unsafe update name");
        ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
        var request=(HttpWebRequest)WebRequest.Create(BaseUrl+name);
        request.AllowAutoRedirect=false;request.Timeout=12000;request.ReadWriteTimeout=30000;request.Proxy=null;
        request.UserAgent="ElsFriendsGitBootstrap/42";request.Headers[HttpRequestHeader.CacheControl]="no-cache";
        request.ServerCertificateValidationCallback=delegate(object sender,X509Certificate cert,X509Chain chain,SslPolicyErrors errors){return Certificate(cert,DateTime.UtcNow);};
        var response=(HttpWebResponse)request.GetResponse();
        if(response.StatusCode!=HttpStatusCode.OK){response.Dispose();throw new IOException("Update endpoint unavailable");}return response;
    }
    public static string ReadBounded(Stream source,int limit) {
        using(var buffer=new MemoryStream()) {
            byte[] data=new byte[4096];int read;
            while((read=source.Read(data,0,data.Length))>0){if(buffer.Length+read>limit)throw new InvalidDataException("Release metadata too large");buffer.Write(data,0,read);}
            return Encoding.UTF8.GetString(buffer.ToArray());
        }
    }
    static ElsGitRelease Latest() {
        using(var response=Open("latest.json"))using(var stream=response.GetResponseStream())return Verify(ReadBounded(stream,32768));
    }
    public static void WriteDownloaded(Stream input,string output,ElsGitRelease release) {
        using(var file=new FileStream(output,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
            byte[] data=new byte[65536];long total=0;int read;
            while((read=input.Read(data,0,data.Length))>0){total+=read;if(total>release.Size)throw new InvalidDataException("Update exceeds signed size");file.Write(data,0,read);}
            if(total!=release.Size)throw new EndOfStreamException("Incomplete update");file.Flush(true);
        }
        if(!ValidFile(output,release))throw new InvalidDataException("Update checksum differs");
    }
    static void Commit(string temporary,string destination) {
        RegularTree(destination);if(File.Exists(destination))File.Replace(temporary,destination,null);else File.Move(temporary,destination);
    }
    public static void NoDowngrade(ElsGitRelease prior,ElsGitRelease next) {
        if(prior!=null&&prior.Version>next.Version)throw new InvalidDataException("Release downgrade rejected");
    }
    static string Quote(string value) { return "\""+value.Replace("\"","\\\"")+"\""; }
    public static string Arguments(string root) { return "--local --local-source "+Quote(Repository(root)); }
    public static string Prepare(string root) {
        root=Repository(root);string cache=Path.Combine(root,".launcher-cache");RegularTree(cache);Directory.CreateDirectory(cache);
        string identity;using(var sha=SHA256.Create())identity=Hex(sha.ComputeHash(Encoding.UTF8.GetBytes(root.ToUpperInvariant()))).Substring(0,24);
        bool owned=false;using(var mutex=new Mutex(false,"Local\\ElsGitLauncher-"+identity)) {
            try {
                try{owned=mutex.WaitOne(0);}catch(AbandonedMutexException){owned=true;}
                if(!owned)throw new IOException("本仓库正在准备统一启动器，请稍后重试。");
                string ready=Path.Combine(cache,"ready.json");RegularTree(ready);ElsGitRelease prior=null;
                if(File.Exists(ready))prior=Verify(File.ReadAllText(ready,Encoding.UTF8));
                ElsGitRelease next;
                try{next=Latest();}catch(WebException) {
                    if(prior!=null){RequireCurrent(prior);string old=Path.Combine(cache,prior.FileName);if(ValidFile(old,prior))return old;}throw;
                }
                RequireCurrent(next);NoDowngrade(prior,next);
                string destination=Path.Combine(cache,next.FileName);RegularTree(destination);
                if(!ValidFile(destination,next)) {
                    string temporary=Path.Combine(cache,"download-"+Guid.NewGuid().ToString("N")+".part");
                    try {
                        using(var response=Open(next.FileName))using(var input=response.GetResponseStream()) {
                            if(response.ContentLength>=0&&response.ContentLength!=next.Size)throw new InvalidDataException("Update size differs");
                            WriteDownloaded(input,temporary,next);
                        }
                        Commit(temporary,destination);
                    }finally{if(File.Exists(temporary))File.Delete(temporary);}
                }
                string metadata=Path.Combine(cache,"ready-"+Guid.NewGuid().ToString("N")+".part");
                try{File.WriteAllText(metadata,next.Envelope,new UTF8Encoding(false));Commit(metadata,ready);}finally{if(File.Exists(metadata))File.Delete(metadata);}
                return destination;
            }finally{if(owned)mutex.ReleaseMutex();}
        }
    }
    public static void Run(string path) {
        string root=Repository(path),launcher=Prepare(root);
        using(var child=Process.Start(new ProcessStartInfo(launcher,Arguments(root)){UseShellExecute=false,WorkingDirectory=root})){}
    }
}
'@

if (-not $LibraryOnly) {
    try {
        Write-Host '正在校验统一启动器，首次运行可能需要下载…'
        [ElsGitLauncher]::Run($RepositoryRoot)
    } catch {
        Write-Host ('统一启动器准备失败：' + $_.Exception.Message) -ForegroundColor Red
        Write-Host '未启动游戏，也未修改已有存档。请检查网络、仓库完整性或联系维护者。'
        exit 1
    }
}
