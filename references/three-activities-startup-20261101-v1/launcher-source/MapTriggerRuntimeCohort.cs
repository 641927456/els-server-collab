using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class MapTriggerRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-map-trigger-20261031-v1",LocalPayload="074114c170660fe78ca1c47009c0d501e7df43594078937065d162175f6248af",LocalEnvelope="39724880909ada4c4feb86d0b3d10a6e8a65ab19a4c4f07472c333ae49e4fcfe",LocalMetadata="c8d168e606528dbc35aa8a232bba46a7c17e363ec5bea35a2a73d430fd4bbea5",BootstrapHash="928f96ab60b42110c619dc5f4fdeca6a45eb6dd1c1cec25d6f34a19c67231361",LocalResource="ElsFriends.MapTriggerLocalRuntimeFiles",BootstrapResource="ElsFriends.MapTriggerLocalBootstrap";
  internal const string FriendsPayload="d562e49be717320f85be884f61455abda2660730da1bde92dcb5a41a59a350fc",FriendsEnvelope="10fb645028e8f41d6b6e78eed28404988e326f41e599088cf2b25d5ab4cf8137",FriendsProfileHash="2afa3470bae6df28c7e2fc2a70e7ef55a4b39d5755dc5ee84c6afca8249e0393",FriendsResource="ElsFriends.MapTriggerFriendsRuntimeFiles";
  internal const int LocalCount=1804,FriendsCount=1789;
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
