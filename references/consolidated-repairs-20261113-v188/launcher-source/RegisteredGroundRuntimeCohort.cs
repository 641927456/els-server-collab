using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class RegisteredGroundRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-registered-ground-items-20261101-v1",LocalPayload="72bdad15e0f9c6d1919ace445c01796cbca53e8300b02c7baa13b65bf9f3ae9c",LocalEnvelope="cfcda8b56b75d65b7bd5fee103ee6e44b7e1e32838300965ee89085a9e3430fe",LocalMetadata="c9c1fc0fe22ff0737f25b42f8cff72b1b1276ee0926739f7cdecc1266b6d7397",BootstrapHash="94bd4ce682dce7ab5b39c7d73b3cb6f3e5762fdcb45550026d686f5696216205",LocalResource="ElsFriends.RegisteredGroundLocalRuntimeFiles",BootstrapResource="ElsFriends.RegisteredGroundLocalBootstrap";
  internal const string FriendsPayload="7802e22ad2023e8de1679665ae5a0ab50884cb095ad73055fc41473c6c217dd7",FriendsEnvelope="e28ba7da9248cf19e76c2c222446b8596c2127253a518de9e5336e4cc31093d7",FriendsProfileHash="28580d61fcfd06491a01982979b78e3fd0cad112cf32ad61aae4f100f30e3084",FriendsResource="ElsFriends.RegisteredGroundFriendsRuntimeFiles";
  internal const int LocalCount=1887,FriendsCount=1798;
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
