using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class GrowthGuideRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-growth-guide-20261101-v1",LocalPayload="c72e3a915e8d9f69318eb94ae0b7d14cacfd1f533384b7eead01c5e673950c34",LocalEnvelope="8363c1e54336e8b1e49fc11d0780ad8d04bffee1c6ba717b3dd79b7e02b157d6",LocalMetadata="f3ff040a7e1f854407ec0193e120490551ef1dac86ea27b8e23d691956ae3272",BootstrapHash="003e117bd7cc3bca81c38f71af59ac64944dda52c63d36c488e40047259e5341",LocalResource="ElsFriends.GrowthGuideLocalRuntimeFiles",BootstrapResource="ElsFriends.GrowthGuideLocalBootstrap";
  internal const string FriendsPayload="19f87f1b0ea00614aff5fc17bad0e5fa01a83340c9f7262f351c341e9685fed3",FriendsEnvelope="c55bb1e7025790914d109fdf3512e1092e40f347ec3c6a7382a6a8956cf1dd65",FriendsProfileHash="e3e0047d679b071bfdada097b43817b9f4803688d65c64bdbb45396073baa7f3",FriendsResource="ElsFriends.QuestGatesFriendsRuntimeFiles";
  internal const int LocalCount=1911,FriendsCount=1800;
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
