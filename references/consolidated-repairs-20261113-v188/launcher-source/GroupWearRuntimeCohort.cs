using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class GroupWearRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-group-wear-20261101-v1",LocalPayload="775a67fc4d07296701eba7f9762df3612b12444247238572074d89d772864e2e",LocalEnvelope="ffa5b6efca369b64ebf886fb5e6667aa2a465a997e2fc501f00101057d8b3dd3",LocalMetadata="3f5076858a4060be1d56a3be7946d8d6145a72b53b1f76fa93416eb0f1abfe12",BootstrapHash="2d9ca0cb0bc0034d0fe333bf256111519282a65c2a42ebd47d69f664cc2d8d7f",LocalResource="ElsFriends.GroupWearLocalRuntimeFiles",BootstrapResource="ElsFriends.GroupWearLocalBootstrap";
  internal const string FriendsPayload="4964d5154490273bd3d54b7c95a729e898b1eae099bd6aa9592102048fd7209f",FriendsEnvelope="424722426c30ebc2da3c07a5524bbe069df96fdaa168d7a6987da0386073d4d7",FriendsProfileHash="7d135dc2da5362491dfcc12ccfa14de22da7bb9b0d2f516fd11607dcdd47f014",FriendsResource="ElsFriends.GroupWearFriendsRuntimeFiles";
  internal const int LocalCount=1880,FriendsCount=1794;
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
