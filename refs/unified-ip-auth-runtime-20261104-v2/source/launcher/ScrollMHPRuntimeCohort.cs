using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class ScrollMHPRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-scroll-mhp-20261101-v1",LocalPayload="170577fec4502e76ca1f49ed2298143c16a05dffc76b6518fd638fa39850eb7b",LocalEnvelope="380811ed513c44d8e6b16151b4876894370c247474a77718b18d815a04186a30",LocalMetadata="5ba698c67f219fadfe2fe08f4345686e80d4bb71615ae80e177cc3584d967c41",BootstrapHash="81d346af68db1874e4bf8a15415451091e2962923fd742557c61e6da0541210e",LocalResource="ElsFriends.ScrollMHPLocalRuntimeFiles",BootstrapResource="ElsFriends.ScrollMHPLocalBootstrap";
  internal const string FriendsPayload="19f87f1b0ea00614aff5fc17bad0e5fa01a83340c9f7262f351c341e9685fed3",FriendsEnvelope="c55bb1e7025790914d109fdf3512e1092e40f347ec3c6a7382a6a8956cf1dd65",FriendsProfileHash="e3e0047d679b071bfdada097b43817b9f4803688d65c64bdbb45396073baa7f3",FriendsResource="ElsFriends.QuestGatesFriendsRuntimeFiles";
  internal const int LocalCount=1930,FriendsCount=1800;
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
