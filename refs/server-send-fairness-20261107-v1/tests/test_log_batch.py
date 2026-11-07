import contextlib,importlib.util,io,json,os,sys,tempfile,threading,types,unittest
from pathlib import Path
H=Path(__file__).resolve().parent
p=H.parent/'source/els_server/observability.py'
spec=importlib.util.spec_from_file_location('tested_event_log',p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
class LogBatchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='owned-log-check-',dir=H);self.root=Path(self.tmp.name);self.logs=[];self.releases=[]
  self.original_time=m.time;self.output=contextlib.redirect_stdout(io.StringIO());self.output.__enter__()
 def tearDown(self):
  for event in self.releases:event.set()
  for log in self.logs:log.close()
  m.time=self.original_time;self.output.__exit__(None,None,None);self.tmp.cleanup()
 def log(self,name):
  root=self.root/name;log=m.EventLog(types.SimpleNamespace(log_dir=root,log_max_bytes=1024*1024,log_backups=2));self.logs.append(log);return log,root
 def rows(self,root):return [json.loads(line)for line in(root/'server.jsonl').read_text('utf8').splitlines()]
 def pause(self):
  entered=threading.Event();release=threading.Event();self.releases.append(release)
  def sleep(seconds):entered.set();release.wait(3)
  m.time=types.SimpleNamespace(sleep=sleep);return entered,release
 def test_order_frozen_values_and_batched_file_emits(self):
  entered,release=self.pause();log,root=self.log('ordered');handler=log.logger.handlers[0];emit=handler.emit;calls=[]
  def record(row):calls.append(row.getMessage());emit(row)
  handler.emit=record;values=[1,2]
  log('request_timing',sequence=0,data=values);self.assertTrue(entered.wait(2))
  for n in range(1,101):log('request_timing',sequence=n,data=values)
  log('operational_failure',sequence=101);values.append(99);release.set();log.close()
  rows=self.rows(root);self.assertEqual([v['sequence']for v in rows],list(range(102)))
  self.assertTrue(all(v['data']==[1,2]for v in rows if v['sequence']<101));self.assertLess(len(calls),20)
 def test_critical_first_uses_no_diagnostic_window(self):
  delays=[];m.time=types.SimpleNamespace(sleep=delays.append);log,root=self.log('critical');handler=log.logger.handlers[0];emit=handler.emit;done=threading.Event()
  def record(row):emit(row);done.set()
  handler.emit=record;log('operational_failure',sequence=0);self.assertTrue(done.wait(2));self.assertFalse(delays);log.close()
  self.assertEqual([v['sequence']for v in self.rows(root)],[0])
 def test_full_queue_keeps_critical_fallback_and_accounts_drops(self):
  entered,release=self.pause();log,root=self.log('overflow');log('request_timing',sequence=0);self.assertTrue(entered.wait(2))
  with log.queue.mutex:log.queue.maxsize=1
  log('request_timing',sequence=1);log('request_timing',sequence=2);log('operational_failure',sequence=3)
  self.assertTrue(any(v.get('sequence')==3 for v in self.rows(root)))
  release.set();log.close();rows=self.rows(root)
  self.assertEqual({v.get('sequence')for v in rows if v['event']=='request_timing'},{0,1})
  self.assertTrue(any(v['event']=='log_overflow'and v['dropped']=={'request_timing':1}for v in rows))
if __name__=='__main__':unittest.main()
