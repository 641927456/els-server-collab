using System;
using System.IO;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace ElsFriends {
    // Sixth cohort. Every V46 and older constant/resource remains a separate,
    // immutable predecessor. Empty final fields reject selection and Prepare.
    static class NextAccessoryCohort {
        internal const string Profile="channels/accessory-identification-accepted-20261031-v1.json";
        internal const string Release="local-accessory-identification-groups-20261030-v1";
        internal const string ManagedRelease="local-git-first-run-accessory-identification-20261031-v1";
        internal const string ProfileHash="3f7002d2e2b5601d9ec2225bda47fc80b75646bea2cd22d29e8fcdcb3e9aab32",FormalHash="8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69",RowsHash="d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999",SourceSetHash="250a0581df1ca0cb945786c4cfb699b419997b66d24141fa9d02eb444d2ee2f8";
        internal const string LocalPayload="201c28a1efb7a5c64a6f9f5998a5af770aced95ffebfefc12614c1eaef92c444",LocalEnvelope="1719deff1d845338fc8160eaad1f01805552144d4779977e29099c9cca4c3cf7",LocalMetadata="836dd3b532e63cf22f95771ec234f5de3696e004655b9cdf8ceb5a080698e4da",BootstrapHash="54b835e0049593999753ae2c03520fe337b96f71ee8d8180f5e90a8f525307b6";
        internal const string FriendsPayload="5fae76e54c6cdb54206c6c50dec44c34b9964c6a2fdaf7ada2f627cb50c3f01e",FriendsEnvelope="bae7e490cd5174227ebc350bc9224ce7f43b4516d64d66d05468c50d9b85fc45",FriendsProfileHash="3b33c9f256b8e388006b79f84679873b3588a32f849565ab079a8fbd0a77621a",FriendsSourceSetHash="250a0581df1ca0cb945786c4cfb699b419997b66d24141fa9d02eb444d2ee2f8";
        internal const string RawUpdaterHash="2bf58b58b906b2f2c18abe9061eb6aa99986e985fa714097f08fbeebdf751e92";
        internal const string LocalResource="ElsFriends.AccessoryLocalRuntimeFiles";
        internal const string FriendsResource="ElsFriends.AccessoryFriendsRuntimeFiles";
        internal const string BootstrapResource="ElsFriends.AccessoryLocalBootstrap";
        internal const string RawUpdaterResource="ElsFriends.AccessoryRawLocalUpdater";
        internal const int SourceCount=1342,LocalCount=1796,FriendsCount=1781;
        internal static readonly bool FriendsDefaultEnabled=true;
        static bool Hash(string s) {return Regex.IsMatch(s??"","^[a-f0-9]{64}$");}
        internal static bool SourceReady {get{return Hash(ProfileHash)&&Hash(FormalHash)&&Hash(RowsHash)&&Hash(SourceSetHash);}}
        internal static bool IsSource(LocalCohortSnapshot s) {
            return s!=null&&!s.Legacy&&SourceReady&&s.Profile==Profile&&s.ProfileHash==ProfileHash&&s.SourceRelease==Release&&s.FormalHash==FormalHash&&s.SourceRowsHash==RowsHash;
        }
        internal static void RequireLocal() {
            if(!SourceReady||!Hash(LocalPayload)||!Hash(LocalEnvelope)||!Hash(LocalMetadata)||!Hash(BootstrapHash))throw new IOException("Accessory exact LOCAL source/signature bindings pending");
        }
        internal static void RequireFriends() {
            if(!SourceReady||!Hash(FriendsPayload)||!Hash(FriendsEnvelope)||!Hash(FriendsProfileHash)||!Hash(FriendsSourceSetHash))throw new IOException("Accessory exact Friends signature bindings pending");
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
