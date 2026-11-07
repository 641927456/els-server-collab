"""Verify the common repair through the real Application worker/read scope."""
import hashlib,json,struct,time,unittest
from pathlib import Path
import test_lifecycle as t

HERE=Path(__file__).resolve().parent
f=t.f


class Worker(t.Repaired):
    def close_app(self):
        registry=self.app.registry
        if registry is not None:
            self.app.executor.submit(registry.close).result()
            self.app.registry=None
        self.app.close()

    def send_worker(self,kind,qid):
        self.seq+=1
        body=(struct.pack('>ii',qid,f.quest_catalog().quest(qid)['m_eStartNPCID']) if kind==0xee
              else struct.pack('>iiI5B',qid,0,0,0,0,1,1,0))
        event=f.Event(0x202,performers=(0,),kind=kind,payload=body)
        # Same _worker_call as Application.call, without a listener/event loop.
        return f.encoded(self.app.executor.submit(self.app._worker_call,
            self.s.handle,(event,self.seq),{},time.perf_counter()).result(timeout=30))

    def test_committed_reward_level_visible_inside_worker_read_scope(self):
        self.historical_parent()
        self.town(20001)
        f.sql(self.path,'UPDATE reward_balances SET experience=? WHERE uid=?',
              (f.client_data().thresholds[1]-1,self.uid))
        self.observe_level()
        self.assertNotIn(100020,self.active())
        reply=self.send_worker(0xee,30140)
        self.assertEqual(next(e for e in reply if e.kind==0xef).payload,bytes(4))
        reply=self.send_worker(0xf4,30140)
        self.assertEqual(next(e for e in reply if e.kind==0xf5).payload[:4],bytes(4))
        self.assertGreaterEqual(self.actor.character()['level'],2)
        self.assertIn(100020,self.active())
        self.assertTrue(any(e.kind==0xf0 and struct.unpack_from('>i',e.payload)[0]==100020 for e in reply))
        self.assertNotIn(100020,self.state.completed())


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        Worker('test_committed_reward_level_visible_inside_worker_read_scope')]))
    f.tmp.cleanup()
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),skipped=len(result.skipped),
        real_Application_worker_call=True,real_FriendsSession_handle=True,
        committed_reads=True,source=t.json.loads((HERE/'tests.json').read_bytes())['modules'],
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        private_SQL_removed=not f.PRIVATE.exists(),production_DB_used=False,
        network=False,natural_GUI=False,natural_combat=False)
    (HERE/'worker-tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
