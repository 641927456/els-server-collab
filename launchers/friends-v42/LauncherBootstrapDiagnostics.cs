using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace ElsFriends {
    // Only the launcher's selected, bounded attempt metadata is collected here.
    // Full game diagnostics remain in the existing, verified Python helper.
    // This path needs no Python, component download or access to game files.
    static class LauncherBootstrapDiagnostics {
        static JavaScriptSerializer Json(){return new JavaScriptSerializer {MaxJsonLength=65536,RecursionLimit=12};}
        static string UnderData(string relative) {
            if(String.IsNullOrEmpty(relative)||Path.IsPathRooted(relative)||relative.Contains(':'))throw new IOException("Invalid launcher path");
            var parts=relative.Replace('\\','/').Split('/');if(parts.Any(p=>p.Length==0||p=="."||p==".."))throw new IOException("Invalid launcher path");
            string root=Path.GetFullPath(Program.DataRoot),path=Path.GetFullPath(Path.Combine(root,Path.Combine(parts)));
            if(!path.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Path outside launcher");
            for(string current=path;current!=null;current=Path.GetDirectoryName(current)) {
                if((File.Exists(current)||Directory.Exists(current))&&(File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked diagnostic path");
                if(String.Equals(current,root,StringComparison.OrdinalIgnoreCase))return path;
            }
            throw new IOException("Path outside launcher");
        }
        public static string RuntimeRelative(string path) {
            string root=Path.GetFullPath(Program.DataRoot),full=Path.GetFullPath(path);
            if(!full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Runtime outside launcher");
            string relative=full.Substring(root.Length+1).Replace('\\','/');ResolveRuntime(relative);return relative;
        }
        public static string ResolveRuntime(string relative) {
            var parts=(relative??"").Replace('\\','/').Split('/');if(parts.Length!=2||(parts[0]!="versions"&&parts[0]!="component-runtimes")||!Regex.IsMatch(parts[1],"^[a-f0-9]{16}(?:-[a-f0-9]{12}(?:-repair-[a-f0-9]{12})?)?$"))throw new IOException("Unsupported diagnostic runtime");
            return UnderData(relative);
        }
        static string Redact(string value,string token) {
            value=value??"";
            if(!String.IsNullOrEmpty(token))value=value.Replace(token,"<redacted>");
            value=Regex.Replace(value,@"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----","<private-key-redacted>",RegexOptions.Singleline);
            value=Regex.Replace(value,@"(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+","$1 <redacted>");
            value=Regex.Replace(value,@"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s""']+","$1<user>");
            value=Regex.Replace(value,@"(?i)((?:password|passwd|passphrase|token|authorization|cookie|secret|login|argument|密码|口令|令牌|私钥|密钥)[""']?\s*[:=：]\s*)(?:""[^""\r\n]*""|'[^'\r\n]*'|[^\s,;，。}]+)","$1<redacted>");
            value=Regex.Replace(value,@"(?i)(--(?:password|token|secret|api-key)\s+)(?:""[^""]*""|\S+)","$1<redacted>");
            value=Regex.Replace(value,@"(?i)((?:密码|口令|令牌|私钥|密钥|password|passwd|token)(?:\s+(?:is\s+)?|(?:是|为)\s*))[^\s,;，。}]+","$1<redacted>");
            return value.Length<=2000?value:value.Substring(0,2000);
        }
        static byte[] Encode(object value){return Encoding.UTF8.GetBytes(Json().Serialize(value));}
        static string Digest(byte[] value){using(var stream=new MemoryStream(value))return Program.Hash(stream);}
        public static DiagnosticBundle Generate(string attempt,string description,string token) {
            if(attempt!=null&&!Regex.IsMatch(attempt,"^[a-f0-9]{32}$"))throw new IOException("Invalid diagnostic attempt");
            var members=new SortedDictionary<string,byte[]>(StringComparer.Ordinal);var omissions=new List<string>{"runtime_unavailable:launcher_metadata_only","game_logs_not_collected_without_runtime"};
            var meta=new Dictionary<string,object>();
            if(attempt!=null)try {
                string path=UnderData("logs/attempts/"+attempt+"/attempt.json");if(new FileInfo(path).Length>65536)throw new IOException("Attempt metadata size");
                var original=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));if(Convert.ToString(original["attempt_id"])!=attempt)throw new IOException("Attempt metadata differs");
                meta["schema"]=1;meta["attempt_id"]=attempt;
                foreach(string field in new[]{"started_utc","ended_utc"}){object raw;DateTimeOffset time;if(original.TryGetValue(field,out raw)&&DateTimeOffset.TryParse(Convert.ToString(raw),out time))meta[field]=time.ToUniversalTime().ToString("o");}
                object value;if(original.TryGetValue("payload",out value)&&Regex.IsMatch(Convert.ToString(value),"^[a-f0-9]{64}$"))meta["payload"]=value;
                if(original.TryGetValue("phase",out value)&&new[]{"starting","login","authentication_failed","component_update","component_update_failed","preflight","preflight_failed","game_running","game_exit","game_failed","launcher_error","client_not_selected","credentials_missing"}.Contains(Convert.ToString(value)))meta["phase"]=value;
                if(original.TryGetValue("component_error_type",out value)&&Regex.IsMatch(Convert.ToString(value),"^[A-Za-z0-9]{1,70}Exception$"))meta["component_error_type"]=value;
                if(original.TryGetValue("component_failure",out value)) {
                    var failure=value as Dictionary<string,object>;var safe=new Dictionary<string,object>();object raw;
                    if(failure!=null){if(failure.TryGetValue("artifact",out raw)&&Regex.IsMatch(Convert.ToString(raw),"^(?:runtime-[a-f0-9]{64}\\.zip|blob-[a-f0-9]{64}\\.bin)$"))safe["artifact"]=raw;if(failure.TryGetValue("error_type",out raw)&&Regex.IsMatch(Convert.ToString(raw),"^[A-Za-z0-9]{1,70}Exception$"))safe["error_type"]=raw;foreach(string field in new[]{"expected_bytes","attempts"})if(failure.TryGetValue(field,out raw)&&(raw is int||raw is long)&&Convert.ToInt64(raw)>=0&&Convert.ToInt64(raw)<=536870912)safe[field]=raw;}
                    if(safe.Count>0)meta["component_failure"]=safe;
                }
                members["attempt.json"]=Encode(meta);
            }catch{omissions.Add("attempt_metadata_unavailable");}
            var classification=new {code="launcher_runtime_unavailable",certainty="observed_stage",reason="运行组件尚未就绪；仅收集所选启动器记录，完整游戏日志需环境可用后采集。"};
            members["system.json"]=Encode(new {os=Environment.OSVersion.Platform.ToString(),version=Environment.OSVersion.Version.ToString(),process_64_bit=Environment.Is64BitProcess,launcher_version=AutoUpdate.Version});
            members["summary.json"]=Encode(new {schema=1,attempt_id=attempt,created_utc=DateTimeOffset.UtcNow.ToString("o"),payload=Program.PayloadHash,description=Redact(description,token),classification=classification,omissions=omissions,collection="explicit_player_action",raw_binaries_included=false,launcher_metadata_only=true});
            members["manifest.json"]=Encode(new {schema=1,files=members.ToDictionary(row=>row.Key,row=>Digest(row.Value))});
            string id=Guid.NewGuid().ToString("N"),relative="diagnostics/outgoing/"+id+".zip",archive=UnderData(relative);
            Program.PrivateWrite(Path.Combine(Path.GetDirectoryName(archive),".private"),"");long expanded=members.Values.Sum(v=>(long)v.Length);
            using(var output=new FileStream(archive,FileMode.CreateNew,FileAccess.Write,FileShare.None))using(var zip=new ZipArchive(output,ZipArchiveMode.Create))foreach(var row in members){var entry=zip.CreateEntry(row.Key,CompressionLevel.NoCompression);using(var stream=entry.Open())stream.Write(row.Value,0,row.Value.Length);}
            return new DiagnosticBundle {Archive=archive,RequestId=id,AttemptId=attempt,Description=description,Files=members.Keys.ToArray(),Omissions=omissions.ToArray(),Bytes=new FileInfo(archive).Length,ExpandedBytes=expanded,Classification=classification.reason,Bootstrap=true};
        }
        static readonly byte[] Magic=Encoding.ASCII.GetBytes("ELS-FRIENDS/1\n");
        static void WriteReply(Stream stream,object value){byte[] body=Encode(value);if(body.Length<1||body.Length>2048)throw new IOException("Diagnostic request size");stream.Write(Magic,0,Magic.Length);stream.WriteByte((byte)(body.Length>>8));stream.WriteByte((byte)body.Length);stream.Write(body,0,body.Length);stream.Flush();}
        static Dictionary<string,object> ReadReply(Stream stream){if(!Program.Exact(stream,Magic.Length).SequenceEqual(Magic))throw new IOException("Unexpected diagnostic server");byte[] size=Program.Exact(stream,2);int length=size[0]*256+size[1];if(length<1||length>2048)throw new IOException("Diagnostic response size");return Json().Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(Program.Exact(stream,length)));}
        internal static string Exchange(Stream stream,byte[] body,string name,string token,string requestId) {
            WriteReply(stream,new {op="diagnostic_upload",name=name,token=token,size=body.Length,sha256=Digest(body),request_id=requestId});var result=ReadReply(stream);
            object ready;if(result.TryGetValue("ready",out ready)&&Object.Equals(ready,true)){stream.Write(body,0,body.Length);stream.Flush();result=ReadReply(stream);}
            object report;string id=result.TryGetValue("report_id",out report)?Convert.ToString(report):"";if(!Program.Ok(result)||!Regex.IsMatch(id,"^D[0-9]{8}-[a-f0-9]{16}$"))throw new IOException("Diagnostic upload not confirmed");return id;
        }
        public static string Upload(DiagnosticBundle bundle,string name,string token) {
            if(String.IsNullOrEmpty(name)||String.IsNullOrEmpty(token)||!Regex.IsMatch(bundle.RequestId??"","^[a-f0-9]{32}$"))throw new IOException("Diagnostic login required");
            string path=UnderData("diagnostics/outgoing/"+bundle.RequestId+".zip");if(!String.Equals(path,Path.GetFullPath(bundle.Archive),StringComparison.OrdinalIgnoreCase))throw new IOException("Diagnostic bundle path differs");
            long size=new FileInfo(path).Length;if(size<1||size>2*1024*1024)throw new IOException("Diagnostic upload size");byte[] body=File.ReadAllBytes(path);
            using(var tcp=new TcpClient()){if(!tcp.ConnectAsync(Program.Host,19400).Wait(8000))throw new IOException("Connection timeout");tcp.ReceiveTimeout=10000;tcp.SendTimeout=10000;
                using(var ssl=new SslStream(tcp.GetStream(),false,delegate(object sender,System.Security.Cryptography.X509Certificates.X509Certificate cert,System.Security.Cryptography.X509Certificates.X509Chain chain,SslPolicyErrors errors){if(cert==null)return false;using(var sha=SHA256.Create())return Program.Hex(sha.ComputeHash(cert.GetRawCertData()))==Program.Pin;})) {
                    ssl.ReadTimeout=10000;ssl.WriteTimeout=10000;ssl.AuthenticateAsClient(Program.Host,null,SslProtocols.Tls12,false);return Exchange(ssl,body,name,token,bundle.RequestId);
                }
            }
        }
    }
}
