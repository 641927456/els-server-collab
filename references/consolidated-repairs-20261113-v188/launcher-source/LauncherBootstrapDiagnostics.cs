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
        static string PrivateBlocks(string value,bool truncated=false) {
            // A live log may end before END; a bounded tail may start after BEGIN.
            value=Regex.Replace(value,@"-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\z)","<private-key-redacted>",RegexOptions.Singleline);
            if(truncated)value=Regex.Replace(value,@"\A.*?-----END [^-]*PRIVATE KEY-----","<private-key-fragment-redacted>",RegexOptions.Singleline);
            return value;
        }
        static string Redact(string value,string token,int limit=2000) {
            value=value??"";
            if(!String.IsNullOrEmpty(token))value=value.Replace(token,"<redacted>");
            value=PrivateBlocks(value);
            value=Regex.Replace(value,@"(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+","$1 <redacted>");
            value=Regex.Replace(value,@"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s""']+","$1<user>");
            value=Regex.Replace(value,@"(?i)((?:password|passwd|passphrase|token|authorization|cookie|secret|login|argument|密码|口令|令牌|私钥|密钥)[""']?\s*[:=：]\s*)(?:""[^""\r\n]*""|'[^'\r\n]*'|[^\s,;，。}]+)","$1<redacted>");
            value=Regex.Replace(value,@"(?i)(--(?:password|token|secret|api-key)\s+)(?:""[^""]*""|\S+)","$1<redacted>");
            value=Regex.Replace(value,@"(?i)((?:密码|口令|令牌|私钥|密钥|password|passwd|token)(?:\s+(?:is\s+)?|(?:是|为)\s*))[^\s,;，。}]+","$1<redacted>");
            return value.Length<=limit?value:value.Substring(0,limit);
        }
        static object SafeLogValue(object value,string token,int depth=0) {
            if(depth>12)return "<depth-limit>";
            var fields=value as Dictionary<string,object>;
            if(fields!=null) {
                var safe=new Dictionary<string,object>();
                object eventValue,typeValue;
                bool errorText=(fields.TryGetValue("event",out eventValue)&&Regex.IsMatch(Convert.ToString(eventValue),"error|fatal|exception|dialog",RegexOptions.IgnoreCase))
                    ||(fields.TryGetValue("type",out typeValue)&&Convert.ToString(typeValue)=="error");
                foreach(var row in fields.Take(128)) {
                    string key=row.Key;
                    if(Regex.IsMatch(key,@"password|passwd|passphrase|token|authorization|cookie|secret|private.?key|session.?key|login$|argument$|密码|口令|令牌|私钥|密钥",RegexOptions.IgnoreCase))safe[key]="<redacted>";
                    else if(errorText&&(key=="text"||key=="message")&&row.Value is string)safe[key]=Redact((string)row.Value,token,12000);
                    else if(Regex.IsMatch(key,@"^(hex|wire_hex|data_hex|payload_hex|encrypted_hex|plaintext|packet|body|text|message|chat|commandline|data|bytes|buffer|content)$",RegexOptions.IgnoreCase)||(String.Equals(key,"payload",StringComparison.OrdinalIgnoreCase)&&!(row.Value is Dictionary<string,object>))) {
                        byte[] raw=Encode(row.Value);safe[key+"_summary"]=new {bytes=raw.Length,sha256=Digest(raw)};
                    } else safe[key]=SafeLogValue(row.Value,token,depth+1);
                }
                return safe;
            }
            if(value is string)return Redact((string)value,token,12000);
            var sequence=value as System.Collections.IEnumerable;
            if(sequence!=null)return sequence.Cast<object>().Take(512).Select(item=>SafeLogValue(item,token,depth+1)).ToArray();
            return value;
        }
        static bool JsonStart(string record) {
            if(record.Length==0)return false;
            if(record[0]=='{'){string member=record.Substring(1).TrimStart();return member.Length==0||member[0]=='"'||member[0]=='}';}
            if(record[0]!='[')return false;
            if(Regex.IsMatch(record,@"^\[[^{}\[\]""\r\n]+\][ \t]+\S"))return false;
            string value=record.Substring(1).TrimStart();
            if(value.Length==0||"[{\"]".IndexOf(value[0])>=0)return true;
            return Regex.IsMatch(value,@"^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=\s*(?:,|\]|$))");
        }
        static bool JsonRecord(string[] lines,int first,string opening,out int last,out string record,out string suffix) {
            var result=new StringBuilder();int depth=0;bool quoted=false,escaped=false;
            for(last=first;last<lines.Length;last++) {
                string line=last==first?opening:lines[last];
                for(int i=0;i<line.Length;i++) {
                    char c=line[i];result.Append(c);
                    if(quoted){if(escaped)escaped=false;else if(c=='\\')escaped=true;else if(c=='"')quoted=false;continue;}
                    if(c=='"')quoted=true;
                    else if(c=='{'||c=='[')depth++;
                    else if((c=='}'||c==']')&&--depth==0){record=result.ToString();suffix=line.Substring(i+1);return true;}
                }
                result.Append('\n');
            }
            record=null;suffix=null;return false;
        }
        static string LogText(string text,string token,bool truncated,List<string> omissions,string name) {
            var clean=new StringBuilder();string[] lines=PrivateBlocks(text,truncated).Split('\n');bool orphan=truncated;
            for(int index=0;index<lines.Length;index++) {
                string line=lines[index],record=line.TrimStart('\uFEFF',' ','\t','\r'),prefix="";
                if(record.StartsWith("ELS_CLIENT_COMPATIBILITY: ")){prefix="ELS_CLIENT_COMPATIBILITY: ";record=record.Substring(prefix.Length);orphan=false;}
                // A cut-off parent's raw field can contain a complete child object.
                // Its context is unknown until the next ordinary log record.
                if(orphan&&(JsonStart(record)||record.StartsWith("}")||record.StartsWith("]")
                    ||Regex.IsMatch(record,@"^""(?:[^""\\]|\\.)*""\s*(?::|,|$)")
                    ||Regex.IsMatch(record,@"^(?:true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*,?\s*$"))) {
                    if(!omissions.Contains("logs/"+name+":leading_json_fragment"))omissions.Add("logs/"+name+":leading_json_fragment");
                    continue;
                }
                if(!JsonStart(record)) {if(record.Length>0)orphan=false;clean.AppendLine(Redact(line,token,12000));continue;}
                int last;string full,suffix;
                if(!JsonRecord(lines,index,record,out last,out full,out suffix)){omissions.Add("logs/"+name+":incomplete_json_record");break;}
                index=last;
                try {clean.AppendLine(prefix+Json().Serialize(SafeLogValue(Json().DeserializeObject(full),token))+Redact(suffix,token,12000));}
                catch(ArgumentException){if(!omissions.Contains("logs/"+name+":invalid_json_record"))omissions.Add("logs/"+name+":invalid_json_record");}
                catch(InvalidOperationException){if(!omissions.Contains("logs/"+name+":invalid_json_record"))omissions.Add("logs/"+name+":invalid_json_record");}
            }
            return clean.ToString();
        }
        static void AttemptLogs(string attempt,string token,SortedDictionary<string,byte[]> members,List<string> omissions) {
            if(attempt==null)return;
            foreach(string name in new[]{"client-check.log","game-launch.log"}) {
                try {
                    string path=UnderData("logs/attempts/"+attempt+"/"+name);
                    if(!File.Exists(path)){omissions.Add("logs/"+name+":missing");continue;}
                    const int limit=256*1024;byte[] raw;bool truncated;
                    using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite)) {
                        long length=stream.Length;truncated=length>limit;stream.Position=Math.Max(0,length-limit);
                        raw=new byte[(int)Math.Min(length,limit)];int count=0,read;
                        while(count<raw.Length&&(read=stream.Read(raw,count,raw.Length-count))>0)count+=read;
                        if(count!=raw.Length)Array.Resize(ref raw,count);
                    }
                    string text=Encoding.UTF8.GetString(raw);if(truncated){int newline=text.IndexOf('\n');text=newline<0?"":text.Substring(newline+1);omissions.Add("logs/"+name+":tail_256KiB");}
                    byte[] encoded=Encoding.UTF8.GetBytes(LogText(text,token,truncated,omissions,name));
                    if(encoded.Length>512*1024){omissions.Add("logs/"+name+":sanitized_size");continue;}
                    members["logs/"+name]=encoded;
                }catch(IOException){omissions.Add("logs/"+name+":unavailable");}
                catch(UnauthorizedAccessException){omissions.Add("logs/"+name+":unavailable");}
            }
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
                object identitySchema;bool legacyIdentity=!original.TryGetValue("runtime_identity_schema",out identitySchema);bool knownIdentity=identitySchema is int&&Convert.ToInt32(identitySchema)==2;
                bool discloseIdentity=legacyIdentity||(knownIdentity&&original.ContainsKey("runtime_identity_state")&&Convert.ToString(original["runtime_identity_state"])=="verified");
                meta["runtime_identity_state"]=legacyIdentity?"legacy-record":knownIdentity?"unprepared":"unsupported-schema";
                object value;if(discloseIdentity&&original.TryGetValue("payload",out value)&&Regex.IsMatch(Convert.ToString(value),"^[a-f0-9]{64}$"))meta["payload"]=value;
                foreach(string field in new[]{"runtime_manifest_sha256","local_business_manifest_sha256"})if(discloseIdentity&&original.TryGetValue(field,out value)&&Regex.IsMatch(Convert.ToString(value),"^[a-f0-9]{64}$"))meta[field]=value;
                foreach(string field in new[]{"runtime_kind","runtime_identity_state","runtime_release"})if(discloseIdentity&&original.TryGetValue(field,out value)&&Regex.IsMatch(Convert.ToString(value),"^[a-z0-9][a-z0-9-]{0,95}$"))meta[field]=value;
                if(original.TryGetValue("phase",out value)&&new[]{"starting","login","authentication_failed","component_update","component_update_failed","preflight","preflight_failed","game_running","game_exit","game_failed","launcher_error","client_not_selected","credentials_missing"}.Contains(Convert.ToString(value)))meta["phase"]=value;
                if(original.TryGetValue("exit_code",out value)&&(value is int||value is long)&&Convert.ToInt64(value)>=Int32.MinValue&&Convert.ToInt64(value)<=Int32.MaxValue)meta["exit_code"]=value;
                if(original.TryGetValue("component_error_type",out value)&&Regex.IsMatch(Convert.ToString(value),"^[A-Za-z0-9]{1,70}Exception$"))meta["component_error_type"]=value;
                if(original.TryGetValue("component_failure",out value)) {
                    var failure=value as Dictionary<string,object>;var safe=new Dictionary<string,object>();object raw;
                    if(failure!=null){if(failure.TryGetValue("artifact",out raw)&&Regex.IsMatch(Convert.ToString(raw),"^(?:runtime-[a-f0-9]{64}\\.zip|blob-[a-f0-9]{64}\\.bin)$"))safe["artifact"]=raw;if(failure.TryGetValue("error_type",out raw)&&Regex.IsMatch(Convert.ToString(raw),"^[A-Za-z0-9]{1,70}Exception$"))safe["error_type"]=raw;foreach(string field in new[]{"expected_bytes","attempts"})if(failure.TryGetValue(field,out raw)&&(raw is int||raw is long)&&Convert.ToInt64(raw)>=0&&Convert.ToInt64(raw)<=536870912)safe[field]=raw;}
                    if(safe.Count>0)meta["component_failure"]=safe;
                }
                members["attempt.json"]=Encode(meta);
            }catch{omissions.Add("attempt_metadata_unavailable");}
            AttemptLogs(attempt,token,members,omissions);
            var classification=new {code="launcher_metadata_only",certainty="observed_stage",reason="完整诊断工具未能使用；已收集所选启动器记录，不能据此判断运行组件损坏或游戏崩溃原因。"};
            members["system.json"]=Encode(new {os=Environment.OSVersion.Platform.ToString(),version=Environment.OSVersion.Version.ToString(),process_64_bit=Environment.Is64BitProcess,launcher_version=AutoUpdate.Version});
            members["summary.json"]=Encode(new {schema=1,attempt_id=attempt,created_utc=DateTimeOffset.UtcNow.ToString("o"),payload=meta.ContainsKey("payload")?meta["payload"]:null,runtime_kind=meta.ContainsKey("runtime_kind")?meta["runtime_kind"]:null,runtime_manifest_sha256=meta.ContainsKey("runtime_manifest_sha256")?meta["runtime_manifest_sha256"]:null,runtime_identity_state=meta.ContainsKey("runtime_identity_state")?meta["runtime_identity_state"]:"unprepared",description=Redact(description,token),classification=classification,omissions=omissions,collection="explicit_player_action",raw_binaries_included=false,launcher_metadata_only=true});
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
