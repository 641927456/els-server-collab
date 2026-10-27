"""Prevent the generic door fallback from admitting original raid controllers."""
import copy, unittest, uuid
from types import SimpleNamespace as NS
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.fishing_bait_loot import _facts

class Selected597Boundaries(unittest.TestCase):
    def run_at(self,identity,stage,part):
        run=DungeonRun(identity,str(uuid.uuid4()));run._load_stage(stage);run.part=part
        run.defeated={n['key']:b'accepted' for n in run.current['npcs'] if n['active']and n.get('team',1)!=0}
        return run

    def test_local_identity_snapshot_preserves_real_identity(self):
        s=NS(account=NS(get_location=lambda:{'map':30282}),active_map=30282)
        self.assertEqual(_facts(s)[3:5],('None',30282))
        self.assertEqual(_facts(s),_facts(s))
        s.identity={'id':7};self.assertEqual(_facts(s)[3],repr(s.identity))

    def test_both_30282_exits_require_every_active_hostile(self):
        for stage in (0,1):
            run=self.run_at(30282,stage,1);condition=run.current['conditions'][0]
            self.assertTrue(run.condition_ready(condition))
            key=next(n['key']for n in run.current['npcs']if n['active']and n.get('team',1)!=0)
            run.defeated.pop(key);self.assertFalse(run.condition_ready(condition))

    def test_changed_graph_or_changed_door_is_rejected(self):
        for field,value in (('template',6851),('active',True),('no_drop',False),('ally',True),('team',0)):
            run=self.run_at(30282,0,1);gate=next(n for n in run.current['npcs']if n['key_code']==1)
            gate[field]=value
            self.assertFalse(run.condition_ready(run.current['conditions'][0]),field)
        run=self.run_at(30282,0,1);run.graph=copy.deepcopy(run.graph);run.graph['source_sha256']='0'*64
        self.assertFalse(run.condition_ready(run.current['conditions'][0]))

    def test_34140_controller_does_not_become_a_door(self):
        for stage in (0,1,2):
            run=self.run_at(34140,stage,0);condition=run.current['conditions'][0]
            self.assertFalse(run.condition_ready(condition))
            for n in run.current['npcs']:
                if n['template']in condition['required']:run.defeated[n['key']]=b'accepted-controller'
            self.assertTrue(run.condition_ready(condition))

    def test_all_other_kind1_and_kind3_conditions_keep_original_predicate(self):
        from els_server.domain.dungeon_routes import route_catalog
        catalog=route_catalog();cases=0
        for identity in catalog._data['routes']:
            identity=int(identity)
            # Source guards reject encounters requiring contextual admission;
            # this exhaustive condition check uses the pinned graph directly.
            try:run=DungeonRun(identity,str(uuid.uuid4()))
            except (ValueError,KeyError):continue
            if run.encounter:continue
            for stage,source in run.graph['stages'].items():
                run._load_stage(int(stage))
                for part in source['parts']:
                    run.part=int(part)
                    npcs=run.current['npcs'];dead={n['key']:b'accepted'for n in npcs if n['active']and n.get('team',1)!=0}
                    run.defeated=dead
                    for c in run.current['conditions']:
                        if c['kind']not in(1,3)or(identity==30282 and(int(stage),int(part))in((0,1),(1,1))):continue
                        keys=[n['key']for n in npcs if(n['key_code']in c['required']if c['kind']==1 else n['template']in c['required'])]
                        self.assertEqual(run.condition_ready(c),bool(keys)and all(k in dead for k in keys),(identity,stage,part,c))
                        cases+=1
        self.assertGreater(cases,100)

if __name__=='__main__':unittest.main()
