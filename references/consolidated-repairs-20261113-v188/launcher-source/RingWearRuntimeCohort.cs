using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class RingWearRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-ring-wear-20261101-v1",LocalPayload="5046798df783818b7759f10db1b03fa0b425694cb8a962dbe72dbaede95090de",LocalEnvelope="ec5051b7c5dae7576574d5a3b97d282964731a5cd7c887e987b24466f7cec981",LocalMetadata="70ec081512886dbee926639cdfdbbd61e2e182fefe396ee8ce30f5da93e85180",BootstrapHash="de22a4b1f01eae42962e9f14dc0e0600ffd9c95c7d818363814311acea15e156",LocalResource="ElsFriends.RingWearLocalRuntimeFiles",BootstrapResource="ElsFriends.RingWearLocalBootstrap";
  internal const string FriendsPayload="19f87f1b0ea00614aff5fc17bad0e5fa01a83340c9f7262f351c341e9685fed3",FriendsEnvelope="c55bb1e7025790914d109fdf3512e1092e40f347ec3c6a7382a6a8956cf1dd65",FriendsProfileHash="e3e0047d679b071bfdada097b43817b9f4803688d65c64bdbb45396073baa7f3",FriendsResource="ElsFriends.QuestGatesFriendsRuntimeFiles";
  internal const int LocalCount=1892,FriendsCount=1800;
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
