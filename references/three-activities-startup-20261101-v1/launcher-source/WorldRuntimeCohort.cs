using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class WorldRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-world-event-20261031-v1",LocalPayload="767a908a9ca8e18a74d3153056b283226d3dbab24edd5e113a715fb724e06c2d",LocalEnvelope="cd9c20dd6736c5efc50aa4a2090fb15c21db2a5484b02d68b3a8ff402a515be7",LocalMetadata="e4d97944fd696c01534c4c656821d13ed7061c860807d9949aa03c4b2321591d",BootstrapHash="bb7145edac674361b4177d5694f02afe972c64fbcb7c3890a28df538dc0988dc",LocalResource="ElsFriends.WorldLocalRuntimeFiles",BootstrapResource="ElsFriends.WorldLocalBootstrap";
  internal const string FriendsPayload="87bd002d2bb6a924664b3988dfd916e1fd24e41bead128af762eaa31e876aef6",FriendsEnvelope="e52fed8f4101ac913c438898b45f72ffb0340f6c248b42e1e31117a56c43f3a6",FriendsProfileHash="599ee035378124deebaed387d9db8ced333b1d7860bbfe35f2a7d71cd77de83e",FriendsResource="ElsFriends.WorldFriendsRuntimeFiles";
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
