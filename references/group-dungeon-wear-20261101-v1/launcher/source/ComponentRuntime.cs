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
        public static object LastFailure;
        public static string PreparedRoot;
        static RuntimeDefinition preparedDefinition;
        // This observer accepts a path, never a caller-supplied descriptor.
        // Only successful signed Prepare/Available paths set preparedDefinition.
        public static Dictionary<string,object> VerifiedPreparedIdentity(string root) {
            if(preparedDefinition==null||String.IsNullOrEmpty(root)||!String.Equals(System.IO.Path.GetFullPath(root),PreparedRoot,StringComparison.OrdinalIgnoreCase)||!Complete(root,preparedDefinition))throw new IOException("No verified signed runtime selected at this path");
            if(!LaunchMode.Local&&Definition().Identity!=preparedDefinition.Identity)throw new IOException("Prepared helper is not the current signed definition");
            return new Dictionary<string,object>{{"runtime_kind","signed-components"},{"payload",preparedDefinition.Hash},{"runtime_manifest_sha256",preparedDefinition.Identity},{"runtime_identity_state","verified"}};
        }
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
        static RuntimeDefinition LocalDefinition() {
            string text;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends.LocalRuntimeFiles"))using(var reader=new StreamReader(stream,Encoding.UTF8))text=reader.ReadToEnd();
            var def=Verify(text);if(def.Hash!=LocalBootstrap.PayloadHash)throw new IOException("Local runtime binding differs");return def;
        }
        public static string EnsureLocal(Action<string> progress) {
            bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}if(!acquired)throw new IOException("运行环境正在准备，请稍后重试。");return Prepare(LocalDefinition(),progress,LaunchMode.SharedDataRoot);}
                finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        public static string LocalFileManifest(string root) {
            var def=LocalDefinition();if(!Complete(root,def))throw new IOException("本地运行组件校验失败。");
            return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=def.Hash,manifest_sha256=def.Identity,files=def.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});
        }
        internal const string LegacyLocalPayload="70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4";
        internal const string LegacyLocalEnvelope="c0fe16c35b05440258ed372ba2eb67da1419c2de62263e3b8c90aae4b7065371";
        internal const string LegacyLocalMetadata="4688c349a9fb73a592c115ee610261cd9b2ba69cd5e9ccfafdd2b6050be575c1";
        internal const string IdentityLocalEnvelope="ed47a5df4fd5d47bacf297226cce4783866ded16d88074b14d277e9bebeffa04",IdentityLocalMetadata="0a2e4071eb897b8e0b6b210152d305b28bbe571366b95b86f8ed0b5dec54432c";
        internal static string VerifiedLocalResource(string name,string expected) {
            if(!HashText(expected))throw new IOException("LOCAL resource has not received a final accepted binding");
            using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)) {
                if(stream==null||stream.Length>4*1024*1024)throw new IOException("Missing or oversized LOCAL resource");
                using(var data=new MemoryStream()){stream.CopyTo(data);data.Position=0;if(Program.Hash(data)!=expected)throw new IOException("Embedded LOCAL resource identity differs");return Encoding.UTF8.GetString(data.ToArray());}
            }
        }
        static void RequireSelectedLocal(RuntimeDefinition definition,bool legacy) {
            string payload=legacy?LegacyLocalPayload:LocalBootstrap.PayloadHash,metadata=legacy?LegacyLocalMetadata:IdentityLocalMetadata;
            if(definition==null||!HashText(payload)||!HashText(metadata)||definition.Hash!=payload||definition.Files.Count!=1779||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==metadata)!=1)throw new IOException("Selected LOCAL runtime definition crossed source cohorts");
        }
        internal static RuntimeDefinition SelectLocalDefinition(bool legacy) {
            var definition=Verify(VerifiedLocalResource(legacy?"ElsFriends.LegacyLocalRuntimeFiles":"ElsFriends.LocalRuntimeFiles",legacy?LegacyLocalEnvelope:IdentityLocalEnvelope));RequireSelectedLocal(definition,legacy);return definition;
        }
        internal static string EnsureSelectedLocal(RuntimeDefinition definition,bool legacy,Action<string> progress) {
            RequireSelectedLocal(definition,legacy);bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}if(!acquired)throw new IOException("运行环境正在准备，请稍后重试。");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        internal static string SelectedLocalFileManifest(string root,RuntimeDefinition definition,bool legacy) {
            RequireSelectedLocal(definition,legacy);if(!Complete(root,definition))throw new IOException("本地运行组件校验失败。");
            return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});
        }
        // SOURCE ONLY: absent unsigned artifact bindings are an unconditional stop.
        internal const string STRUCTUREPayload="d4481559a4c0ffff4bc4b94855d7ae5dcbfc67f5295a1f7428da69de9cce02d7",STRUCTUREEnvelope="e11a4123f68270db611b7b5fda991c8630b9650a6de2a842d3c447b8d762cfc0";
        internal const string STRUCTUREMetadata="8acdfd6bbfcdc02af18ee29e3e8b1fbffcc9b48370de5d83806fb7424a6e0c27";
        static void RequireSTRUCTURELocal(RuntimeDefinition definition) {
            if(!HashText(STRUCTUREPayload)||!HashText(STRUCTUREEnvelope)||!HashText(STRUCTUREMetadata))throw new IOException("STRUCTURE signed artifact bindings are pending; no runtime preparation is authorized");
            if(definition==null||definition.Hash!=STRUCTUREPayload||definition.Files.Count!=1786||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==STRUCTUREMetadata)!=1)throw new IOException("STRUCTURE runtime crossed its exact source descriptor");
        }
        // Nullable LOCAL and Friends definitions are independent, unsigned and unbound.
        internal const string RepairLocalPayload="0e3efdb292016dee1904d86c463ac35165496ec9524cc5d7ea89a3c7325fb9b5",RepairLocalEnvelope="5004c9eccdbe717c41581c42c0b56658bb23009fdeebda21b7e5050380a81af8",RepairLocalMetadata="2adb90a9bd462e004fa7b8861fa3f9af91161ba383f778f85843f915a2010daa",RepairLocalResource="ElsFriends.RepairLocalRuntimeFiles";
        internal static readonly int? RepairLocalCount=1794;
        internal static readonly bool RepairFriendsDefaultEnabled=true;
        internal const string RepairFriendsPayload="d1dc111b6b9af3a61c3e5c395fa088a7043bfa4686ec7010780ada718287d275",RepairFriendsEnvelope="c0aae17be562667d80753cf2aa7eec5a16c6cc4e37b59508fd296795e33ffd18",RepairFriendsProfileHash="3b33c9f256b8e388006b79f84679873b3588a32f849565ab079a8fbd0a77621a",RepairFriendsResource="ElsFriends.RepairFriendsRuntimeFiles",RepairFriendsSourceSet="15e03f6eef5f258e1f826d7afff7f345a6244e4ca8f7205acf934fd9f8302bbd";
        internal static readonly int? RepairFriendsCount=1779;
        static void RequireRepairLocalBindings() {
            if(!SourceUpdate.RepairBindingsReady||!HashText(RepairLocalPayload)||!HashText(RepairLocalEnvelope)||!HashText(RepairLocalMetadata)||!RepairLocalCount.HasValue||String.IsNullOrEmpty(RepairLocalResource)||String.IsNullOrEmpty(LocalBootstrap.RepairManagedRelease)||!HashText(LocalBootstrap.RepairBootstrapHash)||String.IsNullOrEmpty(LocalBootstrap.RepairBootstrapResource))throw new IOException("Repair LOCAL source/artifact bindings pending; stop before Prepare");
        }
        static void RequireRepairLocal(RuntimeDefinition definition) {
            RequireRepairLocalBindings();
            if(definition==null||definition.Hash!=RepairLocalPayload||definition.Files.Count!=RepairLocalCount.Value||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==RepairLocalMetadata)!=1)throw new IOException("Repair LOCAL crossed its exact signed descriptor");
        }
        static void RequireRepairFriendsBindings() {
            if(!HashText(RepairFriendsPayload)||!HashText(RepairFriendsEnvelope)||!HashText(RepairFriendsProfileHash)||!HashText(RepairFriendsSourceSet)||!RepairFriendsCount.HasValue||String.IsNullOrEmpty(RepairFriendsResource))throw new IOException("Repair Friends source/artifact bindings pending; stop before Prepare");
        }
        internal static RuntimeDefinition SelectRepairFriendsDefinition() {
            RequireRepairFriendsBindings();var definition=Verify(VerifiedLocalResource(RepairFriendsResource,RepairFriendsEnvelope));
            if(definition.Hash!=RepairFriendsPayload||definition.Files.Count!=RepairFriendsCount.Value||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==RepairFriendsProfileHash)!=1)throw new IOException("Repair Friends crossed its own signed descriptor");return definition;
        }
        static void RequireAccessoryLocal(RuntimeDefinition definition) {
            GroupWearRuntimeCohort.RequireLocal();
            if(definition==null||definition.Hash!=GroupWearRuntimeCohort.LocalPayload||definition.Files.Count!=GroupWearRuntimeCohort.LocalCount||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==GroupWearRuntimeCohort.LocalMetadata)!=1)throw new IOException("Accessory LOCAL crossed signed identity");
        }
        static RuntimeDefinition SelectGroupWearFriendsDefinition() {
            var definition=Verify(VerifiedLocalResource(GroupWearRuntimeCohort.FriendsResource,GroupWearRuntimeCohort.FriendsEnvelope));
            if(definition.Hash!=GroupWearRuntimeCohort.FriendsPayload||definition.Files.Count!=GroupWearRuntimeCohort.FriendsCount||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==GroupWearRuntimeCohort.FriendsProfileHash)!=1)throw new IOException("Shop Friends crossed signed identity");return definition;
        }
        static RuntimeDefinition SelectShopFriendsDefinition() {
            var definition=Verify(VerifiedLocalResource(ShopFriendsCohort.FriendsResource,ShopFriendsCohort.FriendsEnvelope));
            if(definition.Hash!=ShopFriendsCohort.FriendsPayload||definition.Files.Count!=ShopFriendsCohort.FriendsCount||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==ShopFriendsCohort.FriendsProfileHash)!=1)throw new IOException("Shop Friends crossed signed identity");return definition;
        }
        static RuntimeDefinition SelectAccessoryFriendsDefinition() {
            NextAccessoryCohort.RequireFriends();var definition=Verify(VerifiedLocalResource(NextAccessoryCohort.FriendsResource,NextAccessoryCohort.FriendsEnvelope));
            if(definition.Hash!=NextAccessoryCohort.FriendsPayload||definition.Files.Count!=NextAccessoryCohort.FriendsCount||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==NextAccessoryCohort.FriendsProfileHash)!=1)throw new IOException("Accessory Friends crossed signed identity");return definition;
        }
        static void RequireOwnedStonesLocal(RuntimeDefinition definition) {
            NextOwnedStonesCohort.RequireLocal();
            if(definition==null||definition.Hash!=NextOwnedStonesCohort.LocalPayload||definition.Files.Count!=NextOwnedStonesCohort.LocalCount||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==NextOwnedStonesCohort.LocalMetadata)!=1)throw new IOException("OwnedStones LOCAL crossed signed identity");
        }
        static RuntimeDefinition SelectOwnedStonesFriendsDefinition() {
            NextOwnedStonesCohort.RequireFriends();var definition=Verify(VerifiedLocalResource(NextOwnedStonesCohort.FriendsResource,NextOwnedStonesCohort.FriendsEnvelope));
            if(definition.Hash!=NextOwnedStonesCohort.FriendsPayload||definition.Files.Count!=NextOwnedStonesCohort.FriendsCount||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==NextOwnedStonesCohort.FriendsProfileHash)!=1)throw new IOException("OwnedStones Friends crossed signed identity");return definition;
        }
        static void RequireCache41400Local(RuntimeDefinition definition) {
            NextCacheCohort.RequireLocal();
            if(definition==null||definition.Hash!=NextCacheCohort.LocalPayload||definition.Files.Count!=NextCacheCohort.LocalCount||definition.Files.Count(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==NextCacheCohort.LocalMetadata)!=1)throw new IOException("Cache41400 LOCAL crossed signed identity");
        }
        static RuntimeDefinition SelectCache41400FriendsDefinition() {
            NextCacheCohort.RequireFriends();var definition=Verify(VerifiedLocalResource(NextCacheCohort.FriendsResource,NextCacheCohort.FriendsEnvelope));
            if(definition.Hash!=NextCacheCohort.FriendsPayload||definition.Files.Count!=NextCacheCohort.FriendsCount||definition.Files.Count(f=>f.Path=="tools/client_compatibility_profiles.json"&&f.Hash==NextCacheCohort.FriendsProfileHash)!=1)throw new IOException("Cache41400 Friends crossed signed identity");return definition;
        }
        internal static RuntimeDefinition SelectLocalDefinition(LocalCohortSnapshot source) {
            SourceUpdate.RequireKnownCohort(source);
            if(source.Accessory){GroupWearRuntimeCohort.RequireLocal();var next=Verify(VerifiedLocalResource(GroupWearRuntimeCohort.LocalResource,GroupWearRuntimeCohort.LocalEnvelope));RequireAccessoryLocal(next);return next;}
            if(source.OwnedStones){NextOwnedStonesCohort.RequireLocal();var next=Verify(VerifiedLocalResource(NextOwnedStonesCohort.LocalResource,NextOwnedStonesCohort.LocalEnvelope));RequireOwnedStonesLocal(next);return next;}
            if(source.Cache41400){NextCacheCohort.RequireLocal();var next=Verify(VerifiedLocalResource(NextCacheCohort.LocalResource,NextCacheCohort.LocalEnvelope));RequireCache41400Local(next);return next;}
            if(source.Repair){RequireRepairLocalBindings();var repair=Verify(VerifiedLocalResource(RepairLocalResource,RepairLocalEnvelope));RequireRepairLocal(repair);return repair;}
            if(!source.Structural)return SelectLocalDefinition(source.Legacy);
            if(!HashText(STRUCTUREPayload)||!HashText(STRUCTUREEnvelope)||!HashText(STRUCTUREMetadata))throw new IOException("STRUCTURE signed artifact bindings are pending");
            var definition=Verify(VerifiedLocalResource("ElsFriends.STRUCTURELocalRuntimeFiles",STRUCTUREEnvelope));RequireSTRUCTURELocal(definition);return definition;
        }
        internal static string EnsureSelectedLocal(RuntimeDefinition definition,LocalCohortSnapshot source,Action<string> progress) {
            SourceUpdate.RequireKnownCohort(source);
            if(source.Accessory){RequireAccessoryLocal(definition);bool repairAcquired=false;using(var repairMutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{repairAcquired=repairMutex.WaitOne(0);}catch(AbandonedMutexException){repairAcquired=true;}if(!repairAcquired)throw new IOException("Runtime preparation already active");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(repairAcquired)repairMutex.ReleaseMutex();}}}
            if(source.OwnedStones){RequireOwnedStonesLocal(definition);bool repairAcquired=false;using(var repairMutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{repairAcquired=repairMutex.WaitOne(0);}catch(AbandonedMutexException){repairAcquired=true;}if(!repairAcquired)throw new IOException("Runtime preparation already active");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(repairAcquired)repairMutex.ReleaseMutex();}}}
            if(source.Cache41400){RequireCache41400Local(definition);bool repairAcquired=false;using(var repairMutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{repairAcquired=repairMutex.WaitOne(0);}catch(AbandonedMutexException){repairAcquired=true;}if(!repairAcquired)throw new IOException("Runtime preparation already active");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(repairAcquired)repairMutex.ReleaseMutex();}}}
            if(source.Repair){RequireRepairLocal(definition);bool repairAcquired=false;using(var repairMutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{repairAcquired=repairMutex.WaitOne(0);}catch(AbandonedMutexException){repairAcquired=true;}if(!repairAcquired)throw new IOException("Runtime preparation already active");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(repairAcquired)repairMutex.ReleaseMutex();}}}
            if(!source.Structural)return EnsureSelectedLocal(definition,source.Legacy,progress);
            RequireSTRUCTURELocal(definition);bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}if(!acquired)throw new IOException("Runtime preparation already active");return Prepare(definition,progress,LaunchMode.SharedDataRoot);}
                finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        internal static string SelectedLocalFileManifest(string root,RuntimeDefinition definition,LocalCohortSnapshot source) {
            SourceUpdate.RequireKnownCohort(source);
            if(source.Accessory){RequireAccessoryLocal(definition);if(!Complete(root,definition))throw new IOException("Repair LOCAL runtime incomplete");return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});}
            if(source.OwnedStones){RequireOwnedStonesLocal(definition);if(!Complete(root,definition))throw new IOException("Repair LOCAL runtime incomplete");return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});}
            if(source.Cache41400){RequireCache41400Local(definition);if(!Complete(root,definition))throw new IOException("Repair LOCAL runtime incomplete");return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});}
            if(source.Repair){RequireRepairLocal(definition);if(!Complete(root,definition))throw new IOException("Repair LOCAL runtime incomplete");return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});}
            if(!source.Structural)return SelectedLocalFileManifest(root,definition,source.Legacy);
            RequireSTRUCTURELocal(definition);if(!Complete(root,definition))throw new IOException("STRUCTURE runtime component verification failed");
            return new JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Serialize(new {payload_sha256=definition.Hash,manifest_sha256=definition.Identity,files=definition.Files.Select(f=>new {path=f.Path,size=f.Size,sha256=f.Hash}).ToArray()});
        }
        static RuntimeDefinition Definition() {
            // Pending stage deliberately retains d366. Enabling a new default
            // without every independent Friends binding throws before Prepare.
            if(TestManifest==null)return SelectGroupWearFriendsDefinition();
            if(ShopFriendsCohort.FriendsDefaultEnabled&&TestManifest==null)return SelectShopFriendsDefinition();
            if(NextAccessoryCohort.FriendsDefaultEnabled&&TestManifest==null)return SelectAccessoryFriendsDefinition();
            if(NextOwnedStonesCohort.FriendsDefaultEnabled&&TestManifest==null)return SelectOwnedStonesFriendsDefinition();
            if(NextCacheCohort.FriendsDefaultEnabled&&TestManifest==null)return SelectCache41400FriendsDefinition();
            if(RepairFriendsDefaultEnabled&&TestManifest==null)return SelectRepairFriendsDefinition();
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
        static void CopyChecked(Stream source,string destination,long size,string hash,Action<long> progress=null) {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(destination));
            using(var target=new FileStream(destination,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                byte[] buffer=new byte[65536];long total=0;int count;
                while((count=source.Read(buffer,0,buffer.Length))>0){total+=count;if(total>size)throw new InvalidDataException("Component exceeds signed size");target.Write(buffer,0,count);if(progress!=null)progress(total);}
                if(total!=size)throw new EndOfStreamException("Truncated component");target.Flush(true);
            }
            if(Digest(destination)!=hash)throw new InvalidDataException("Component checksum differs");
        }
        static bool Retryable(Exception error) {
            var web=error as System.Net.WebException;
            if(web!=null)return web.Status==System.Net.WebExceptionStatus.Timeout||web.Status==System.Net.WebExceptionStatus.ConnectFailure||web.Status==System.Net.WebExceptionStatus.ConnectionClosed||web.Status==System.Net.WebExceptionStatus.ReceiveFailure||web.Status==System.Net.WebExceptionStatus.KeepAliveFailure;
            return error is EndOfStreamException||error.GetType()==typeof(IOException);
        }
        static void DownloadChecked(string name,string destination,long size,string hash,Action<string> progress,string label) {
            for(int attempt=1;attempt<=3;attempt++) {
                var clock=Stopwatch.StartNew();long shown=-1;int percent=-1;
                Action<long> report=delegate(long count){int value=size==0?100:(int)(count*100/size);if(count==0||count==size||value!=percent||clock.ElapsedMilliseconds-shown>=500){shown=clock.ElapsedMilliseconds;percent=value;progress(label+" · "+value+"%（"+(count/1048576.0).ToString("0.0")+" / "+(size/1048576.0).ToString("0.0")+" MiB）"+(attempt>1?" · 重试 "+attempt+"/3":""));}};
                report(0);
                try {using(var input=Open(name))CopyChecked(input,destination,size,hash,report);LastFailure=null;return;}
                catch(Exception error) {
                    LastFailure=new {artifact=name,expected_bytes=size,attempts=attempt,error_type=error.GetType().Name};
                    if(File.Exists(destination))File.Delete(destination);
                    if(attempt==3||!Retryable(error))throw;
                    progress("连接中断，正在重试运行组件（"+(attempt+1)+" / 3）…");Thread.Sleep(attempt*250);
                }
            }
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
        static List<string> Sources(string components,string dataRoot=null) {
            var result=new List<string>();foreach(string root in new[]{System.IO.Path.Combine(dataRoot??Program.DataRoot,"versions"),components})if(Directory.Exists(root)) {
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
            LastFailure=null;
            bool acquired=false;using(var mutex=new Mutex(false,"Local\\ElsFriendsRuntime-"+WindowsIdentity.GetCurrent().User.Value)) {
                try {try{acquired=mutex.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}if(!acquired)throw new IOException("Runtime preparation already active");return Prepare(Definition(),progress);}
                finally{if(acquired)mutex.ReleaseMutex();}
            }
        }
        public static string Available() {
            // Diagnostic collection must not require a successful download.
            // Execute an existing helper only from a complete signed runtime.
            var def=Definition();string components=System.IO.Path.GetFullPath(System.IO.Path.Combine(Program.DataRoot,"component-runtimes"));
            if(!Directory.Exists(components))return null;
            string target=Under(components,def.Hash.Substring(0,16)+"-"+def.Identity.Substring(0,12));
            foreach(string source in new[]{target}.Concat(Sources(components)).Distinct(StringComparer.OrdinalIgnoreCase))if(Complete(source,def)){preparedDefinition=def;PreparedRoot=source;return source;}
            return null;
        }
        static string Prepare(RuntimeDefinition def,Action<string> progress,string dataRoot=null) {
            dataRoot=dataRoot??Program.DataRoot;
            string components=System.IO.Path.GetFullPath(System.IO.Path.Combine(dataRoot,"component-runtimes"));Directory.CreateDirectory(components);
            if((File.GetAttributes(components)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked component directory");
            string target=Under(components,def.Hash.Substring(0,16)+"-"+def.Identity.Substring(0,12));var sources=Sources(components,dataRoot);
            progress("正在校验运行环境，未变化的文件将直接复用…");
            foreach(string source in new[]{target}.Concat(sources).Distinct(StringComparer.OrdinalIgnoreCase))if(Complete(source,def)) {
                CommitPointer(source,def,dataRoot);LastResult=new {reused_files=def.Files.Count,downloaded_files=0,downloaded_bytes=0L,full_archive_downloaded=false,existing_environment_reused=true};return source;
            }
            string stage=System.IO.Path.Combine(components,"prepare-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(stage);
            int reused=0,downloaded=0;long bytes=0;bool full=false,legacy=false;var missing=new List<RuntimeFile>();
            try {
                foreach(var row in def.Files) {
                    string source=sources.FirstOrDefault(p=>Valid(p,row));
                    if(source==null){missing.Add(row);continue;}
                    string dest=Under(stage,row.Path);using(var file=File.OpenRead(Under(source,row.Path)))CopyChecked(file,dest,row.Size,row.Hash);reused++;
                }
                string packages=System.IO.Path.GetFullPath(System.IO.Path.Combine(dataRoot,"component-packages"));Directory.CreateDirectory(packages);
                if((File.GetAttributes(packages)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked package directory");
                string archive=Under(packages,def.Archive);bool cached=Regular(archive,packages)&&new FileInfo(archive).Length==def.Size&&Digest(archive)==def.Hash;
                if(!cached&&reused==0) {
                    string temporary=archive+"."+Guid.NewGuid().ToString("N")+".part";
                    try {
                        legacy=LegacyArchive(temporary,def);
                        if(!legacy){DownloadChecked(def.Archive,temporary,def.Size,def.Hash,progress,"首次下载运行环境");bytes+=def.Size;full=true;}
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
                    DownloadChecked("blob-"+row.Hash+".bin",Under(stage,row.Path),row.Size,row.Hash,progress,"更新运行组件 "+(downloaded+1)+" / "+missing.Count);downloaded++;bytes+=row.Size;
                }
                if(!Complete(stage,def))throw new IOException("Prepared runtime validation failed");
                File.WriteAllText(System.IO.Path.Combine(stage,".complete"),def.Hash);
                // Every old environment remains intact. A corrupt target is
                // never overwritten, since an existing game may still use it.
                if(Directory.Exists(target))target+="-repair-"+Guid.NewGuid().ToString("N").Substring(0,12);
                Directory.Move(stage,target);CommitPointer(target,def,dataRoot);
                LastResult=new {reused_files=reused,downloaded_files=full?missing.Count:downloaded,downloaded_bytes=bytes,full_archive_downloaded=full,legacy_archive_reused=legacy,existing_environment_reused=false};return target;
            }finally{CleanupOwnStage(stage,components);}
        }
        static void CommitPointer(string path,RuntimeDefinition def,string dataRoot=null) {Program.PrivateWrite(System.IO.Path.Combine(dataRoot??Program.DataRoot,"component-state","current.json"),Program.Json.Serialize(new {path=path,payload_sha256=def.Hash,manifest_sha256=def.Identity}));preparedDefinition=def;PreparedRoot=path;}
    }
}
