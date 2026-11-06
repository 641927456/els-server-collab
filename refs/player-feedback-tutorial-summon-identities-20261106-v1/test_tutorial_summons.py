"""Exercise the real tutorial run and shared authenticated summon handler."""
from pathlib import Path
import hashlib,json,struct,sys,unittest
from types import ModuleType
fixture_path=Path(__file__).with_name('test_repairs.py')
fixture=ModuleType('repairs_fixture');fixture.__file__=str(fixture_path)
source=fixture_path.read_text('utf8')
assert source.count('\nnames=[x for x in sys.argv[1:]')==1
exec(compile(source.split('\nnames=[x for x in sys.argv[1:]')[0],str(fixture_path),'exec'),fixture.__dict__)
Repairs,HOME,BASE,BASELINE=fixture.Repairs,fixture.HOME,fixture.BASE,fixture.BASELINE
from els_server.domain.first_story_population import TutorialRun,catalog
from els_server.domain.dungeon_routes import DungeonRun
from els_server.protocol.protocol_codec import Event

class TutorialSummons(Repairs):
    def test_tutorial_stage_reservations(self):
        maps=sorted(map(int,catalog()._data['maps']))
        assert len(maps)==15
        for identity in maps:
            run=TutorialRun(identity)
            floor=run.summon_key_floor
            assert floor>=16
            for stage in sorted(map(int,run.graph['stages'])):
                run._load_stage(stage)
                assert all(key<floor for key in run.reserved_keys),(identity,stage,floor)
        # The unchanged ordinary-run initialization uses the same reservation.
        run=DungeonRun(30000,'00000000-0000-0000-0000-000000000001')
        assert run.summon_key_floor>=16
        assert all(k<run.summon_key_floor for k in run.reserved_keys)

    def test_tutorial_summon_response_and_replay(self):
        self.career(164)
        from els_server.domain.summon_rules import player_summon_templates
        assert 384 in player_summon_templates(self.account.character())
        from els_server.domain.summons import LAYOUTS
        fixture=json.loads(Path('G:/els/analysis/skills-clear-20261015/sentry-request.json').read_bytes())
        dto=bytearray.fromhex(fixture['dto']);struct.pack_into('<Q',dto,0x6d,self.uid)
        def encode(row):
            chunks=[struct.pack('>I',1)]
            for off,size,xor,kind in next(iter(LAYOUTS.values())):
                if kind=='empty':chunks.append(bytes(4))
                elif size==12:chunks.append(b''.join(row[off+i:off+i+4][::-1]for i in(0,4,8)))
                else:chunks.append((int.from_bytes(row[off:off+size],'little')^xor).to_bytes(size,'big'))
            return b''.join(chunks)
        payload=encode(dto)
        identity=next(int(k)for k,v in catalog()._data['maps'].items()if v.get('unit_type')==5)if any(v.get('unit_type')==5 for v in catalog()._data['maps'].values())else 41410
        if str(identity)not in catalog()._data['maps']:identity=int(next(iter(catalog()._data['maps'])))
        run=TutorialRun(identity)
        self.s.dungeon_run=run;self.s.dungeon_id=identity
        self.s.enter_dungeon=True;self.s.population_test=True
        self.s.phase='dungeon_active';self.s.dungeon_substage_synced=True
        self.s.clear_notified=False;self.s.part_end_notified=False
        request=Event(0x202,kind=0x2ce,payload=payload)
        before=set(run.reserved_keys)
        reply=self.dispatch(request,200)
        assert [e.kind for e in reply]==[0x2cf,0x2d0]
        assert reply[0].payload==bytes(4)
        assert len(self.s.summon_keys)==1 and self.s.summon_keys.isdisjoint(before)
        assert min(self.s.summon_keys)>=run.summon_key_floor
        keys=set(self.s.summon_keys)
        assert self.dispatch(request,200)==reply[:1] and self.s.summon_keys==keys
        corrupt=bytearray(dto);struct.pack_into('<Q',corrupt,0x6d,self.other)
        denied=self.dispatch(Event(0x202,kind=0x2ce,payload=encode(corrupt)),201)
        assert len(denied)==1 and denied[0].kind==0x2cf and denied[0].payload!=bytes(4)
        assert self.s.summon_keys==keys and run.reserved_keys==before

if __name__=='__main__':
    suite=unittest.TestSuite(TutorialSummons(name)for name in('test_tutorial_stage_reservations','test_tutorial_summon_response_and_replay'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    binding=json.loads((HOME/'manifest.json').read_bytes())
    record=dict(baseline=BASELINE,tests=result.testsRun,passed=result.wasSuccessful(),failures=[dict(test=str(t),trace=s)for t,s in result.failures+result.errors],source=[x for x in binding['files']if x['path'].endswith(('dungeon_routes.py','first_story_population.py'))],scope='Actual unified Application/worker dispatch, own temporary stores; phase fixture, no native admission claim')
    (HOME/('tutorial-summons-baseline.json'if BASELINE else'tutorial-summons-fixed.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    raise SystemExit(not result.wasSuccessful())
