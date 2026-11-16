using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class LagPerformanceRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-dungeon-lag-20261101-v1",LocalPayload="5ec562114090c4bff8b8cc22bd0470bca9ddaf2c1f71e0f02df875eff56ba14f",LocalEnvelope="a89e81aed9529f793564244524e85924517576261b07172cc6cdfc3049772965",LocalMetadata="b0b4f345ec9adaae02246f0fb0750db7f3961936c936e27004ab723224649400",BootstrapHash="c73381ceb735383f049533afb99188eb5292e18625bf60209ef4544049c8addc",LocalResource="ElsFriends.LagPerformanceLocalRuntimeFiles",BootstrapResource="ElsFriends.LagPerformanceLocalBootstrap";
  internal const string FriendsPayload="19f87f1b0ea00614aff5fc17bad0e5fa01a83340c9f7262f351c341e9685fed3",FriendsEnvelope="c55bb1e7025790914d109fdf3512e1092e40f347ec3c6a7382a6a8956cf1dd65",FriendsProfileHash="e3e0047d679b071bfdada097b43817b9f4803688d65c64bdbb45396073baa7f3",FriendsResource="ElsFriends.QuestGatesFriendsRuntimeFiles";
  internal const int LocalCount=1914,FriendsCount=1800;
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
