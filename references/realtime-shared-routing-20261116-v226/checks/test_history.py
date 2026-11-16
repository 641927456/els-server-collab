import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--runtime',type=Path,required=True)
options,rest=parser.parse_known_args()
sys.argv[1:]=rest
SRC=options.runtime.resolve(strict=True)
sys.path[:0]=[str(SRC),str(SRC/'vendor')]
spec=importlib.util.spec_from_file_location('candidate_history',ROOT/'source/els_server/gameplay_diagnostics.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class HistoryTests(unittest.TestCase):
    def test_relay_window_does_not_evict_business_error(self):
        h=m.IncidentHistory();base=dict(account_id=1,diagnostic_session='launch1')
        h.record('protocol_error',dict(base,error='original'))
        for i in range(100):h.record('relay_traffic',dict(base,counts={'queued':i},queued_by_target={2:i}))
        rows=h.snapshot(1,'launch1');self.assertEqual(len(rows),5)
        self.assertEqual(rows[0]['error'],'original');self.assertEqual(rows[-1]['counts']['queued'],99)
        self.assertEqual(h.snapshot(2,'launch1'),[]);self.assertEqual(h.snapshot(1,'launch2'),[])
        rows[-1]['counts']['queued']=0;self.assertEqual(h.snapshot(1,'launch1')[-1]['counts']['queued'],99)
    def test_session_and_row_bounds(self):
        h=m.IncidentHistory()
        for i in range(140):h.record('relay_traffic',dict(account_id=i+1,diagnostic_session='launch',counts={}))
        self.assertEqual(len(h.relays),128);self.assertEqual(h.snapshot(1,'launch'),[])
        h.record('relay_traffic',dict(account_id=140,diagnostic_session='launch',oversized='x'*9000))
        self.assertEqual(len(h.snapshot(140,'launch')),1)
if __name__=='__main__':unittest.main(verbosity=2)
