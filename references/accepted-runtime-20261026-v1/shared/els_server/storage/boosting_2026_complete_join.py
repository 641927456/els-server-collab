"""Complete local profile projection joins the same binding/ERP/item transaction."""
from els_server.storage.boosting_2026_join_rewards import JoinedRewardParticipation
from els_server.storage.resonance_2026_profiles import ResonanceProfiles


class CompleteJoinedParticipation(JoinedRewardParticipation):
    def __init__(self,db,original_definition,curve,catalog,stats,*,new_profile_policy):
        super().__init__(db,original_definition,curve,catalog)
        self.profiles=ResonanceProfiles(db,curve,stats,new_profile_policy=new_profile_policy)

    def initialize(self):
        super().initialize();self.profiles.initialize()

    def join(self,*,encode,**request):
        profiles={}
        def complete(out):
            profiles.update(self.profiles.synchronize_account(account=request['account']))
            return encode(dict(out,profile=profiles[request['character']]))
        out=super().join(encode=complete,**request)
        return dict(out,profile=profiles[request['character']])
