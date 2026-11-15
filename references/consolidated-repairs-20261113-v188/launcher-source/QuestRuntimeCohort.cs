using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class QuestRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-quest-exp-native-20261101-v1",LocalPayload="7a43717786c5313e76ce854b5cb0f559d172d6e1acfc569c0942df0661ee2d7e",LocalEnvelope="e5edd51629a893d7ffd0e7029a7dd7c9c8245a1b7f04f00b877580120be8a35b",LocalMetadata="36478a45c0c6b4e0b20982de5035a1addc960ad93848d022eeb568d6c2d9b8c3",BootstrapHash="675780999b47f39ade2aaace0f9b49104fdf251586ac81701ad72f6ee147fc8e",LocalResource="ElsFriends.QuestLocalRuntimeFiles",BootstrapResource="ElsFriends.QuestLocalBootstrap";
  internal const string FriendsPayload="d32bee4eb95bb29818095afb5e0f6fd11604c1dcd16148ef7573a65874082fd8",FriendsEnvelope="194f02b20a0c106fef11cd6347eb0019a6eb31c6ab2d7a6c83aeed2d56e1bccc",FriendsProfileHash="dcb6b81dc07d2b9aecdaa12ef4763d6bff5acc0fdfbcf1251e93cae077e5a020",FriendsResource="ElsFriends.QuestFriendsRuntimeFiles";
  internal const int LocalCount=1877,FriendsCount=1792;
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
