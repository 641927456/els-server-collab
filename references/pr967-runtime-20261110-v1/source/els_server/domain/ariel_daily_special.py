"""Typed, live owned ordinary clear joined to the original reward transaction."""
from dataclasses import dataclass
import uuid
from els_server.domain.ariel_daily_special_rules import rule

@dataclass(frozen=True)
class DailySpecialClear:
    session: object
    account: int
    character: int
    reward_run_id: str
    run_id: str
    dungeon: int
    graph_sha256: str
    stage: int
    part: int
    visits: int
    unit: int

    def validate(self):
        s=self.session
        from els_server.domain.ariel_attendance_flow import authority
        from els_server.domain.dungeon_routes import DungeonRun
        authority(s);r=rule(self.dungeon);run=s.dungeon_run
        if (r is None or type(run)is not DungeonRun or s.account.account_id!=self.account or s.account.uid!=self.character
            or s.reward_run_id!=self.reward_run_id or run.run_id!=self.run_id or run.identity!=self.dungeon or s.dungeon_id!=self.dungeon
            or run.graph['source_sha256']!=self.graph_sha256 or self.graph_sha256!=r['graph_sha256']
            or (run.stage,run.part,run.visits)!=(self.stage,self.part,self.visits)
            or s.phase!='dungeon_active' or not s.dungeon_substage_synced or not s.part_end_notified or s.gate_stage!=self.stage
            or run.next is None or run.next['kind']!=4 or s.clear_notified or not s.reward_test or not s.item_test
            or getattr(s,'dungeon_failed',False) or getattr(s,'active_challenge',None)is not None
            or getattr(s,'challenge_deadline',None)is not None):raise ValueError('Ariel daily active normal clear source')
        if s.account.character()['unit_type']!=self.unit:raise ValueError('Ariel daily current character unit')
        for token in(self.run_id,self.reward_run_id):
            if type(token)is not str or str(uuid.UUID(token))!=token:raise ValueError('Ariel daily canonical run')
        participants=frozenset(getattr(s,'dungeon_participants',(self.character,)))
        if participants==frozenset((self.character,)):
            if self.reward_run_id!=self.run_id:raise ValueError('Ariel daily solo reward identity')
        else:
            from els_server.domain.friends_dungeon import FriendsDungeons,Room
            from els_server.domain.dungeon_equipment_loot_flow import current_lease
            app=getattr(s,'application',None);dispatcher=getattr(getattr(app,'world',None),'dungeons',None)
            if type(dispatcher)is not FriendsDungeons:raise ValueError('Ariel daily shared dispatcher')
            room=dispatcher.room(s)
            if (type(room)is not Room or not 2<=len(room.members)<=4 or s not in room.members
                or room.phase not in('active','part_end')or room.identity!=self.dungeon or room.seed!=self.run_id
                or room.party.get('run')is not room or frozenset(m.account.uid for m in room.members)!=participants
                or any(room.party.get(k)for k in('raid_party','challenge','challenge_pending','solo_challenge'))):raise ValueError('Ariel daily original ordinary shared run')
            for m in room.members:
                if (not current_lease(m)or dispatcher.room(m)is not room or m in dispatcher.world.members
                    or dispatcher.world.party_of.get(m)is not room.party or m.dungeon_run is None or m.dungeon_run.run_id!=self.run_id
                    or m.reward_run_id!=str(uuid.uuid5(uuid.UUID(self.run_id),'reward:'+str(m.account.uid)))):
                    raise ValueError('Ariel daily shared owned generation')
        return r

    def receipt_identity(self):
        self.validate()
        return {k:getattr(self,k)for k in('account','character','reward_run_id','run_id','dungeon','graph_sha256','stage','part','visits','unit')}

def prepare(s):
    run=getattr(s,'dungeon_run',None)
    if run is None or rule(run.identity)is None:return None
    value=DailySpecialClear(s,s.account.account_id,s.account.uid,s.reward_run_id,run.run_id,run.identity,
        run.graph['source_sha256'],run.stage,run.part,run.visits,s.account.character()['unit_type'])
    value.validate();return value
