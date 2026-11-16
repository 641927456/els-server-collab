using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class WearRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-wear-wait-20261031-v1",LocalPayload="458145b1f399cb10095c15769a6057f81a3570dc4f29e9878d7582f29b34a656",LocalEnvelope="a447d5f623f75850deeee35642bccbd0223eac3c43fad0cc66c50f55d539a323",LocalMetadata="c1629eaf234f82a5c1b308b5277054a6b9530e55ceb54e4f6a3a9a666fa6e3f7",BootstrapHash="1eb7584916e1aeb1af59123247bd938afb59e9e949debbb536c2976cb7d8916e",LocalResource="ElsFriends.WearLocalRuntimeFiles",BootstrapResource="ElsFriends.WearLocalBootstrap";
  internal const string FriendsPayload="63181c5e1a3ce3e1cf4aa5fa1140891361a8733b6df44a20daefded6de564ee9",FriendsEnvelope="47dd93a33a353a7741ac47460172d80a0f59543d2386fd581865635bf80be3c7",FriendsProfileHash="7283a15e444c34c4fbb2e36965908751f32f19d3ed410c7f3875020e1c13fd0b",FriendsResource="ElsFriends.WearFriendsRuntimeFiles";
  internal const int LocalCount=1798,FriendsCount=1783;
  internal static void RequireLocal(){NextAccessoryCohort.RequireLocal();}
  internal static bool RequireCurrentDirection(Dictionary<string,object> p,LocalCohortSnapshot source){
   object value;if(!p.TryGetValue("release",out value)||!(value is string))return false;
   string release=(string)value;if(release!=ManagedRelease&&!release.StartsWith(ManagedRelease+"-guarded-",StringComparison.Ordinal))return false;
   if(!NextAccessoryCohort.IsSource(source))throw new IOException("Current wear LOCAL source cannot be downgraded");
   if(Convert.ToString(p["source_release"])!=NextAccessoryCohort.Release||Convert.ToString(p["source_formal_manifest_sha256"])!=NextAccessoryCohort.FormalHash)throw new IOException("Wear LOCAL source identity changed");
   if(release!=ManagedRelease){if(!System.Text.RegularExpressions.Regex.IsMatch(release,"^"+System.Text.RegularExpressions.Regex.Escape(ManagedRelease)+"-guarded-[a-f0-9]{12}$")||Convert.ToString(p["recovery_of"])!=ManagedRelease)throw new IOException("Unknown wear recovery identity");foreach(string k in new[]{"recovery_only","complete_C3_reader_and_data","all_three_guards","selection_reader_compatible_recovery","all_five_selection_readers_retained","new_722531_operations_paused"})if(!p.TryGetValue(k,out value)||!Object.Equals(value,true))throw new IOException("Incomplete wear recovery");}
   return true;
  }
 }
}
