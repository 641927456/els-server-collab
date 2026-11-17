using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class MapStagesRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-dungeon-map-stages-20261101-v1",LocalPayload="87e162bf20869b1a73e4d2eae897d95ff753268647f542270ce103a18a3de194",LocalEnvelope="d32be22173f46c3c0ccf8e5ece0868d9f39ae00601d37740f22f23d291a19d15",LocalMetadata="f442e6d5534f85f9061cedd032b561b8bca28d47b6e50884b0073ad85baf0372",BootstrapHash="720402ddf3f8861f97b22ebc0707d35f5ed59ea5e1826d8c2fca285b361739d1",LocalResource="ElsFriends.MapStagesLocalRuntimeFiles",BootstrapResource="ElsFriends.MapStagesLocalBootstrap";
  internal const string FriendsPayload="bfc1d3c5a0c37772c490d84e8732eca1722fb431fd900a5aeb862275a4f777be",FriendsEnvelope="309f7bb7a3d2407ba301287dc9d25bdeccb9859b7337b98df9d9b0acc67e9179",FriendsProfileHash="535dea7fe69f8ea28288d5021f640b1130196103a3c5f9a94bbc9ddf794a83a7",FriendsResource="ElsFriends.MapStagesFriendsRuntimeFiles";
  internal const int LocalCount=1883,FriendsCount=1796;
  internal static void RequireLocal(){NextAccessoryCohort.RequireLocal();}
  internal static bool RequireCurrentDirection(Dictionary<string,object> p,LocalCohortSnapshot source){
   object value;if(!p.TryGetValue("release",out value)||!(value is string))return false;
   string release=(string)value;if(release!=ManagedRelease&&!release.StartsWith(ManagedRelease+"-guarded-",StringComparison.Ordinal))return false;
   if(!NextAccessoryCohort.IsSource(source))throw new IOException("Current world LOCAL source cannot be downgraded");
   if(Convert.ToString(p["source_release"])!=NextAccessoryCohort.Release||Convert.ToString(p["source_formal_manifest_sha256"])!=NextAccessoryCohort.FormalHash)throw new IOException("World LOCAL source identity changed");
   if(release!=ManagedRelease){if(!System.Text.RegularExpressions.Regex.IsMatch(release,"^"+System.Text.RegularExpressions.Regex.Escape(ManagedRelease)+"-guarded-[a-f0-9]{12}$")||Convert.ToString(p["recovery_of"])!=ManagedRelease)throw new IOException("Unknown world recovery identity");foreach(string k in new[]{"recovery_only","complete_C3_reader_and_data","all_three_guards","selection_reader_compatible_recovery","all_five_selection_readers_retained","new_722531_operations_paused"})if(!p.TryGetValue(k,out value)||!Object.Equals(value,true))throw new IOException("Incomplete world recovery");}
   return true;
  }
 }
}
