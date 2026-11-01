"""Activity native buff composition and session lifecycle; isolated storage."""
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
import json,sqlite3,struct,time,unittest,uuid
from test_fix import Fix,ROOT,HOME
from els_server.domain.selected_2026_pair_runtime import from_pack
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain import elixir_flow
from els_server.domain.boosting_2026_buff import DUNGEONS,TEMPLATE,FACTOR,world_row
from els_server.storage import world_elixirs

class Buff(Fix):
    def setUp(self):
        super().setUp()
        self.manager=from_pack(self.path,ROOT/'els_server/data/selected2026/local-pair.json');self.manager.install()
        self.flow=self.manager(self.account);self.s.activity2026_awards=self.flow
        self.now=int(time.time())
    def join(self):
        result=self.flow.handle(self.s,Event(0x202,performers=(0,),kind=0xd2c,payload=b''),800)
        ack=next(e for e in result if e.kind==0xd2d)
        self.assertEqual(struct.unpack('>i',ack.payload)[0],0)
    def dungeon(self,mid=34810):
        self.s.phase='dungeon_active';self.s.active_map=mid;self.s.dungeon_substage_synced=True
        self.s.dungeon_return_pending=False
        self.s.dungeon_run=SimpleNamespace(identity=mid,run_id=str(uuid.uuid4()),stage=0,part=1,visits=1)
    def rows(self,now=None):
        with closing(sqlite3.connect(self.path))as db:
            db.execute('BEGIN')
            return self.flow.world_rows(db,self.s,self.now if now is None else now)
    def test_join_qualification_finite_maps_deadline_and_database_recheck(self):
        self.dungeon();self.assertEqual(self.rows(),[])
        # A stale/corrupt cached notification must not authorize a native effect.
        self.flow.participation.last=(self.uid,self.uid);self.assertEqual(self.rows(),[])
        self.s.phase='town_ready';self.join()
        for mid in sorted(DUNGEONS):
            self.dungeon(mid);rows=self.rows();self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['template'],TEMPLATE)
            self.assertEqual(struct.unpack_from('>i',world_row(self.uid,rows[0]),8)[0],TEMPLATE)
        for mid in(34090,35380,35680,35400,20001):
            self.dungeon(mid);self.assertEqual(self.rows(),[])
        self.dungeon();self.assertEqual(self.rows(self.flow.configuration['ends']),[])
        self.manager.state['enabled']['growth']=False;self.assertEqual(self.rows(),[])
        self.manager.state['enabled']['growth']=True
        original=self.s.account;self.s.account=self.root.for_character(self.other)
        self.assertEqual(self.rows(),[]);self.s.account=original
    def test_periodic_add_deduplicate_off_clear_and_town_clear(self):
        self.join();self.dungeon()
        response=elixir_flow.periodic(self.s);self.assertTrue(response)
        event=next(e for e in response if e.kind==0x3a3)
        self.assertEqual(struct.unpack_from('>I',event.payload,8)[0],1)
        for e in response:encode_event(e)
        self.assertEqual(elixir_flow.periodic(self.s),[])
        self.manager.state['enabled']['growth']=False
        response=elixir_flow.periodic(self.s);event=next(e for e in response if e.kind==0x3a3)
        self.assertEqual(struct.unpack_from('>I',event.payload,8)[0],0)
        self.assertEqual(elixir_flow.periodic(self.s),[])
        self.manager.state['enabled']['growth']=True
        self.assertTrue(elixir_flow.periodic(self.s))
        self.s.phase='town_ready';self.s.dungeon_run=None
        response=elixir_flow.periodic(self.s);event=next(e for e in response if e.kind==0x3a2)
        self.assertEqual(struct.unpack_from('>I',event.payload)[0],0)
    def test_composes_with_existing_elixir_and_clamps_to_event_end(self):
        self.join();self.dungeon();moment=self.flow.configuration['ends']-10
        from els_server.domain.elixir_items import catalog
        rule=catalog()[710206]
        state=dict(owner=self.uid,revision=1,_moment=moment,rows=[dict(owner=self.uid,template=710206,start=moment-10,end=moment-10+rule['period_seconds'])])
        with closing(sqlite3.connect(self.path))as db:
            db.execute('BEGIN')
            events=elixir_flow.prepare(self.s,cold=True)(db,state,None)
        self.assertEqual(struct.unpack_from('>I',events[0].payload)[0],2)
        rows=self.rows(moment);self.assertEqual(rows[0]['end'],self.flow.configuration['ends'])
        self.assertEqual(rows[0]['end']-rows[0]['start'],10)
        self.assertIn(struct.pack('>i',FACTOR),events[0].payload)

if __name__=='__main__':
    names=['Buff.test_join_qualification_finite_maps_deadline_and_database_recheck',
        'Buff.test_periodic_add_deduplicate_off_clear_and_town_clear',
        'Buff.test_composes_with_existing_elixir_and_clamps_to_event_end']
    import sys
    names=['Buff.'+n for n in sys.argv[1:]]if len(sys.argv)>1 else names
    suite=unittest.defaultTestLoader.loadTestsFromNames(names,module=__import__('__main__'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (HOME/'fix-buff-tests.json').write_text(json.dumps(dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors)),indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful()else 1)
