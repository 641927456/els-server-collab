using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;

namespace ElsFriends {
    // Both modes use these same two signed definitions. Only local hosting
    // acquires the service addon; the server implementation is never forked.
    static class LeanRuntime {
        internal const string ClientIdentity="8ae19b9eef1f3c583d4c7d249769959e2d3608b40718968c9b3f79a4034adbc0",ServerIdentity="b3ce190519a3119bc6f1936898c4c7b91e3ebdee60bd55c64a6e5398ff90425c";
        static readonly Lazy<RuntimeDefinition> client=new Lazy<RuntimeDefinition>(()=>Read("ElsFriends.LeanClientRuntimeFiles",ClientIdentity,"client"));
        static readonly Lazy<RuntimeDefinition> server=new Lazy<RuntimeDefinition>(()=>Read("ElsFriends.LeanServerRuntimeFiles",ServerIdentity,"server-addon"));
        internal static RuntimeDefinition Client {get{return client.Value;}}
        internal static RuntimeDefinition Server {
            get {
                var value=server.Value;
                if(value.RequiredClientIdentity!=Client.Identity||value.SourceRelease!=Client.SourceRelease)throw new IOException("Server addon does not match this client definition");
                return value;
            }
        }
        static RuntimeDefinition Read(string name,string identity,string role) {
            string envelope;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)) {
                if(stream==null)throw new IOException("Signed runtime module resource missing");
                using(var reader=new StreamReader(stream,Encoding.UTF8))envelope=reader.ReadToEnd();
            }
            var value=ComponentRuntime.Verify(envelope);
            if(value.Identity!=identity||value.Role!=role)throw new IOException("Signed runtime module identity differs");return value;
        }
        internal static List<RuntimeFile> LocalFiles {
            get {
                var files=Client.Files.ToDictionary(f=>f.Path,StringComparer.Ordinal);
                foreach(var row in Server.Files) {
                    RuntimeFile old;if(files.TryGetValue(row.Path,out old)) {
                        if(old.Hash!=row.Hash||old.Size!=row.Size)throw new IOException("Conflicting shared runtime module file");
                    }else files.Add(row.Path,row);
                }
                return files.Values.OrderBy(f=>f.Path,StringComparer.Ordinal).ToList();
            }
        }
        internal static bool ServerDownloaded {get{return ComponentRuntime.AvailableModule(Server)!=null;}}
        internal static void RequireServerDownload() {
            if(!ServerDownloaded)throw new IOException("请先点击“下载本地服务端”，完成后再使用本地模式。");
        }
        internal static string LocalManifest(string clientRoot,string serverRoot) {
            ComponentRuntime.FilesAt(clientRoot,Client);ComponentRuntime.FilesAt(serverRoot,Server);
            var clientNames=new HashSet<string>(Client.Files.Select(f=>f.Path),StringComparer.Ordinal);
            return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {
                schema=2,unified_runtime=true,source_online_release=Client.SourceRelease,
                client_identity=Client.Identity,server_identity=Server.Identity,
                files=LocalFiles.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash,module=clientNames.Contains(f.Path)?"client":"server"}).ToArray()});
        }
    }
}
