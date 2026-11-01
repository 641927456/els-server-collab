using System;
using System.IO;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace ElsFriends {
    // Fifth cohort. Every V45 Repair constant/resource remains a separate,
    // immutable predecessor. Empty final fields reject selection and Prepare.
    static class NextCacheCohort {
        internal const string Profile="channels/cache-exact41400-accepted-20261030-v1.json";
        internal const string Release="local-cache-exact41400-20261030-v1";
        internal const string ManagedRelease="local-git-first-run-cache-exact41400-20261030-v1";
        internal const string ProfileHash="951c6b5fbf13c6f7e9eda825c9d13e3e601b4bf8325f876dce04b572d6f08c2c",FormalHash="7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35",RowsHash="bd405d403efec936c3a78a8a1a6eefb1a48debdbcd2f3c6b6e44b7c804430f6e",SourceSetHash="b23656c813133e79069eb34ca2653f830a6802eae4861b302070c5d28495d523";
        internal const string LocalPayload="ee68800402e6dc7ef6e8317d07595ffd4b220034c1477a0f122faf311e9d9d78",LocalEnvelope="bd6ad8dd2301b4c4d8ec24209889c0c32d0a7ebb23bc0385824e7f4ce575defa",LocalMetadata="8df4c6fe66868123516414a9351026c1d5dbec84a42fd26421ea735cd81a349c",BootstrapHash="0f8c4aa7ecb090cd2640f039cf2fd9d9169f0946129f2db192e231885f3e8d5b";
        internal const string FriendsPayload="bee4029f24cd24ad4410d173d78eeab7ee1d1ce08b6f8e115785a30710245eb0",FriendsEnvelope="6c06a3bcc327afaed545dc24702b2eae0618604253ec1fa5d86616b2620602f0",FriendsProfileHash="3b33c9f256b8e388006b79f84679873b3588a32f849565ab079a8fbd0a77621a",FriendsSourceSetHash="6211bbb1a17b02cc82f196ed0c49099f189eca5e4cbcd80b989529c34a89ba0d";
        internal const string RawUpdaterHash="b57a5f4d0c7195f6420d301b8ad37979c17612c04b637d7a0cf2783bfe1b85b5";
        internal const string LocalResource="ElsFriends.Cache41400LocalRuntimeFiles";
        internal const string FriendsResource="ElsFriends.Cache41400FriendsRuntimeFiles";
        internal const string BootstrapResource="ElsFriends.Cache41400LocalBootstrap";
        internal const string RawUpdaterResource="ElsFriends.Cache41400RawLocalUpdater";
        internal const int SourceCount=1340,LocalCount=1794,FriendsCount=1779;
        internal static readonly bool FriendsDefaultEnabled=true;
        static bool Hash(string s) {return Regex.IsMatch(s??"","^[a-f0-9]{64}$");}
        internal static bool SourceReady {get{return Hash(ProfileHash)&&Hash(FormalHash)&&Hash(RowsHash)&&Hash(SourceSetHash);}}
        internal static bool IsSource(LocalCohortSnapshot s) {
            return s!=null&&!s.Legacy&&SourceReady&&s.Profile==Profile&&s.ProfileHash==ProfileHash&&s.SourceRelease==Release&&s.FormalHash==FormalHash&&s.SourceRowsHash==RowsHash;
        }
        internal static void RequireLocal() {
            if(!SourceReady||!Hash(LocalPayload)||!Hash(LocalEnvelope)||!Hash(LocalMetadata)||!Hash(BootstrapHash))throw new IOException("Cache41400 exact LOCAL source/signature bindings pending");
        }
        internal static void RequireFriends() {
            if(!SourceReady||!Hash(FriendsPayload)||!Hash(FriendsEnvelope)||!Hash(FriendsProfileHash)||!Hash(FriendsSourceSetHash))throw new IOException("Cache41400 exact Friends signature bindings pending");
        }
        static string Text(Dictionary<string,object> p,string k) {
            object v;if(!p.TryGetValue(k,out v)||!(v is string))throw new IOException("Missing exact current LOCAL identity");return (string)v;
        }
        // Return true only for our exact new normal/guarded pointer. Old sources
        // must never enter a new runtime; other current pointers use old checks.
        internal static bool RequireCurrentDirection(Dictionary<string,object> p,LocalCohortSnapshot source) {
            string release=Text(p,"release"),rid=Text(p,"source_release"),formal=Text(p,"source_formal_manifest_sha256");
            bool normal=SourceReady&&release==ManagedRelease&&rid==Release&&formal==FormalHash;
            bool guarded=SourceReady&&Regex.IsMatch(release,"^"+Regex.Escape(ManagedRelease)+"-guarded-[a-f0-9]{12}$")&&rid==Release&&formal==FormalHash;
            if(!normal&&!guarded)return false;
            if(!IsSource(source))throw new IOException("Current LOCAL cannot be downgraded to an older Git cohort");
            if(guarded) {
                if(Text(p,"recovery_of")!=ManagedRelease)throw new IOException("Unknown recovery identity");
                foreach(string k in new[]{"recovery_only","compatible_read_only","complete_C3_reader_and_data","all_three_guards"}) {
                    object v;if(!p.TryGetValue(k,out v)||!(v is bool)||(bool)v!=true)throw new IOException("Incomplete compatible recovery pointer");
                }
            }
            return true;
        }
    }
}
