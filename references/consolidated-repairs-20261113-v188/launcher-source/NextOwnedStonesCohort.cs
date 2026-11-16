using System;
using System.IO;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace ElsFriends {
    // Sixth cohort. Every V46 and older constant/resource remains a separate,
    // immutable predecessor. Empty final fields reject selection and Prepare.
    static class NextOwnedStonesCohort {
        internal const string Profile="channels/owned-stones-nine-leaf-accepted-20261030-v1.json";
        internal const string Release="local-owned-stones-nine-leaf-20261030-v1";
        internal const string ManagedRelease="local-git-first-run-owned-stones-nine-leaf-20261030-v1";
        internal const string ProfileHash="76bed17ea60a8c8aeeaef387fd5590aec838adecd07b4124d53cbab7a80309b6",FormalHash="965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558",RowsHash="dbfc5f586a692e6acb240a1dd27ff29995893210550f5ecd8e7d3750a6dd0a41",SourceSetHash="a2b1ff7e286c4de294b9b4a50fd3be0400d3d22248fde686932c3b959b035647";
        internal const string LocalPayload="fdfec5119af224754a2155c739a0d0e4163a1706e31903f2e9e65b6fb678d27c",LocalEnvelope="cedeb7b01f9f1d3da10e968d827897aba412f6146b95e7250c5bfbb028cbc933",LocalMetadata="1088d1049ade31b3d3fd1a515718a6d9875a3e26951b14bff05b96dad6531edf",BootstrapHash="436655aa1271adbd84b955fcff195b06af3b4cf2009ef571c3f908e777956fdd";
        internal const string FriendsPayload="5a9b932593ea1f26e6e84f969476711ba9b7b275a62ab67828e25a19edf7d534",FriendsEnvelope="f67c0ae699a415ddca01cf7fc4aaa670594a6c8be0bce6ec626608489c5cf3cd",FriendsProfileHash="3b33c9f256b8e388006b79f84679873b3588a32f849565ab079a8fbd0a77621a",FriendsSourceSetHash="0ea32bcce1a8e6017ea9c3226f875b05f6ba06fd0557d0cb787a9df0a5eea0a5";
        internal const string RawUpdaterHash="51e7743b4d34b82891bfa8f3e4d17d990f6b1c17b41871861a157feda0bff25a";
        internal const string LocalResource="ElsFriends.OwnedStonesLocalRuntimeFiles";
        internal const string FriendsResource="ElsFriends.OwnedStonesFriendsRuntimeFiles";
        internal const string BootstrapResource="ElsFriends.OwnedStonesLocalBootstrap";
        internal const string RawUpdaterResource="ElsFriends.OwnedStonesRawLocalUpdater";
        internal const int SourceCount=1341,LocalCount=1795,FriendsCount=1780;
        internal static readonly bool FriendsDefaultEnabled=true;
        static bool Hash(string s) {return Regex.IsMatch(s??"","^[a-f0-9]{64}$");}
        internal static bool SourceReady {get{return Hash(ProfileHash)&&Hash(FormalHash)&&Hash(RowsHash)&&Hash(SourceSetHash);}}
        internal static bool IsSource(LocalCohortSnapshot s) {
            return s!=null&&!s.Legacy&&SourceReady&&s.Profile==Profile&&s.ProfileHash==ProfileHash&&s.SourceRelease==Release&&s.FormalHash==FormalHash&&s.SourceRowsHash==RowsHash;
        }
        internal static void RequireLocal() {
            if(!SourceReady||!Hash(LocalPayload)||!Hash(LocalEnvelope)||!Hash(LocalMetadata)||!Hash(BootstrapHash))throw new IOException("OwnedStones exact LOCAL source/signature bindings pending");
        }
        internal static void RequireFriends() {
            if(!SourceReady||!Hash(FriendsPayload)||!Hash(FriendsEnvelope)||!Hash(FriendsProfileHash)||!Hash(FriendsSourceSetHash))throw new IOException("OwnedStones exact Friends signature bindings pending");
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
                foreach(string k in new[]{"recovery_only","complete_C3_reader_and_data","all_three_guards","selection_reader_compatible_recovery","all_five_selection_readers_retained","new_722531_operations_paused"}) {
                    object v;if(!p.TryGetValue(k,out v)||!(v is bool)||(bool)v!=true)throw new IOException("Incomplete compatible recovery pointer");
                }
            }
            return true;
        }
    }
}
