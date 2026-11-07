using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class GiftTitleRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-gift-title-hp-20261101-v1",LocalPayload="22a67737b2734de5bea87879d7fb15fff8a24fc5ab3607d7d05610f7587d9d53",LocalEnvelope="e018ab8dabfec6fc52e9f5aa3ee167fd6f7eca5ba700d530b3a8b3e1609182e2",LocalMetadata="a3188b263edae06e0b80213a22c401c7a19ceb33bdba089b46d719d9baa864f0",BootstrapHash="5756941ad504f908f0c5135583d22204853574a88997d390b3a551131ec1155a",LocalResource="ElsFriends.GiftTitleLocalRuntimeFiles",BootstrapResource="ElsFriends.GiftTitleLocalBootstrap";
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
