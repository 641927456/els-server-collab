using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class GroundFashionRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-ground-fashion-20261101-v1",LocalPayload="0107a5b6e836ad82a10bba5d966de963f1000c4d857902b96b0fd3c5e44bf97b",LocalEnvelope="8b1d4738efd7b7cb6e10fcb0d63310cbdd5a7d98588d04534980451980e09bef",LocalMetadata="2bfab49602c29c98d3fbf2a19e81e90f84d84d8f0bb3a456a0fd54a0eed17847",BootstrapHash="9e53b580a1a9f66433787f1c98da8d72f6e4e42f0e0e8462da5c5b7e325ad5b2",LocalResource="ElsFriends.GroundFashionLocalRuntimeFiles",BootstrapResource="ElsFriends.GroundFashionLocalBootstrap";
  internal const string FriendsPayload="bfc1d3c5a0c37772c490d84e8732eca1722fb431fd900a5aeb862275a4f777be",FriendsEnvelope="309f7bb7a3d2407ba301287dc9d25bdeccb9859b7337b98df9d9b0acc67e9179",FriendsProfileHash="535dea7fe69f8ea28288d5021f640b1130196103a3c5f9a94bbc9ddf794a83a7",FriendsResource="ElsFriends.MapStagesFriendsRuntimeFiles";
  internal const int LocalCount=1885,FriendsCount=1796;
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
