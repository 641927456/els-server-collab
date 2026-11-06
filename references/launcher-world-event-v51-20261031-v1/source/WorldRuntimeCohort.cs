using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class WorldRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-world-event-20261031-v1",LocalPayload="767a908a9ca8e18a74d3153056b283226d3dbab24edd5e113a715fb724e06c2d",LocalEnvelope="cd9c20dd6736c5efc50aa4a2090fb15c21db2a5484b02d68b3a8ff402a515be7",LocalMetadata="e4d97944fd696c01534c4c656821d13ed7061c860807d9949aa03c4b2321591d",BootstrapHash="bb7145edac674361b4177d5694f02afe972c64fbcb7c3890a28df538dc0988dc",LocalResource="ElsFriends.WorldLocalRuntimeFiles",BootstrapResource="ElsFriends.WorldLocalBootstrap";
  internal const string FriendsPayload="78d5659499db6d96b21b81e7aea47af372c13ab84c605e02f08995edd6684721",FriendsEnvelope="fe6325a676cd03287a7ddd46e548c164f30b2e2f3a7219d2310b450735c86f81",FriendsProfileHash="9a3fa17fc90eb0aa8b3b5fd238ec81b75834dff60a92b9116d073f520011ff29",FriendsResource="ElsFriends.WorldFriendsRuntimeFiles";
  internal const int LocalCount=1800,FriendsCount=1785;
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
