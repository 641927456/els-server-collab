"""Actual selected pipeline retains avatar recovery and extends later rewards."""
from contextlib import closing
import sqlite3,uuid
from els_server.domain.boosting_2026_recovered_quests import RecoveringBoostingQuestBinding
from els_server.storage.boosting_2026_chain_rewards import ChainRewards

class ChainGrowthBinding(RecoveringBoostingQuestBinding):
    def __init__(self,original,*,clock,campaign_open,catalogs,curve,stats):
        super().__init__(original,clock=clock,campaign_open=campaign_open)
        from els_server.domain.avatar_equipment_admission_2026 import load_original_policy
        from els_server.domain.avatar_current_selection_2026 import load_original_metadata
        from els_server.domain.avatar_accessory_catalog_2026 import load_original
        from els_server.domain.avatar_equipped_counts_2026 import load_original_membership
        self.avatar=dict(policy=load_original_policy(catalogs['policy']),metadata=load_original_metadata(catalogs['metadata']),
            definitions=load_original(catalogs['definitions']),membership=load_original_membership(catalogs['membership']))
        from els_server.domain.avatar_registry_2026 import load_original_category77,classify_templates
        registry=load_original_category77(catalogs['registry'])
        self.avatar['category77']=classify_templates(tuple(self.avatar['policy'][0]),registry=registry)
        if any(self.avatar['category77'].values()):raise ValueError('Unresolved original owner restriction')
        self.curve,self.stats=curve,stats

    def _store(self,db):return ChainRewards(db,self.original,self.curve,self.stats)

    def _group_admission(self,s):
        """Return only the actual party member's derived durable reward ID.

        Called at the existing loading100 hook. The admitted room, account
        lease and all-member loading barrier are server-owned; a client cannot
        select a UUID or retrospectively attach a completed/shared run.
        """
        if (not self.enabled(s) or not s.reward_test or s.dungeon_run is None
                or s.phase!='dungeon_loading' or getattr(s,'coop_error',None)
                or getattr(s,'social_overflow',False)):
            return None
        app=getattr(s,'application',None)
        if app is None:return None
        from els_server.domain.friends_dungeon import Room
        room=app.world.dungeons.room(s);run=s.dungeon_run
        if (type(room) is not Room or room.phase!='loading' or not room.members
                or s not in room.members or room.seed!=run.run_id or room.identity!=run.identity
                or app.playing.get(s.account.account_id) is not s
                or s.identity['id']!=s.account.account_id
                or not app.registry.enabled(s.account.account_id)
                or app.world.party_of.get(s) is not room.party
                or room.party.get('run') is not room
                or tuple(room.party['members'])!=room.members
                or any(app.world.dungeons.room(m) is not room or room.progress.get(m)!=100 for m in room.members)):
            return None
        participants=frozenset(m.account.uid for m in room.members)
        if len(participants)!=len(room.members) or s.dungeon_participants!=participants:return None
        try:seed=uuid.UUID(room.seed)
        except (ValueError,TypeError,AttributeError):return None
        if str(seed)!=room.seed or seed.version!=4:return None
        reward=str(uuid.uuid5(seed,'reward:'+str(s.account.uid)))
        return reward if s.reward_run_id==reward else None

    def capture(self,s):
        run=s.dungeon_run
        if run is None or run.run_id==s.reward_run_id:
            return super().capture(s)
        reward=self._group_admission(s)
        if reward is None or not self.campaign_open(s,self.clock()):return
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            if self._participant(db,s):
                self._store(db).admit_run(account=s.account.account_id,character=s.account.uid,
                    run_id=reward,dungeon=run.identity)
        # Existing recover_clears consumes that member's already committed
        # RewardState proof, verifies owner/map/accepted generation and updates
        # count+consumed marker atomically. No new clear or reward is fabricated.
