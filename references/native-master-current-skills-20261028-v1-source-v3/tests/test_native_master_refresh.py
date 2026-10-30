"""Current-parent transaction/replay/ownership checks and native wire invariants."""
from pathlib import Path
import contextlib,hashlib,importlib,json,sqlite3,struct,sys,tempfile,unittest
from unittest.mock import patch
G=Path(__file__).resolve().parents[3];V=Path(sys.argv.pop(1)).resolve();channel=sys.argv.pop(1);assert channel in('online','local');H=V.parent;C=G/'references/native-master-current-skills-20261028-v1-source-v3'
sys.path[:0]=[str(V),str(G)]
import els_server.application
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.careers import use_career_item
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.domain.careers import RULES
from els_server.domain.character_rules import CLASSES,default_slots
from els_server.protocol.career_messages import current_skill_notices
from els_server.protocol.protocol_codec import Event
from els_server.storage.seal_quests import load_character
from els_server.domain.skill_rules import learned_skills
from els_server.domain.skill_unlocks import unsealed_skills
manifest=dict(delta=[dict(path=r['path'],candidate_sha256=r['after_sha256'])for r in json.loads((C/'manifest.json').read_bytes())['mutations']if r['channel']==channel])
for row in manifest['delta']:
 module=importlib.import_module(row['path'][:-3].replace('/','.'))
 assert Path(module.__file__).resolve()==(V/row['path']).resolve()
 assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()==row['candidate_sha256']

class MasterCandidateTests(unittest.TestCase):
 def case(self):
  temp=tempfile.TemporaryDirectory(dir=H);assert Path(temp.name).resolve().is_relative_to(H.resolve());self.addCleanup(temp.cleanup);path=Path(temp.name)/'own.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters()
  template,rule=next((t,r)for t,r in RULES.items()if r['kind']=='master_advancement'and r['unit_type']==1)
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET unit_class=?,level=99,transcendence=1 WHERE uid=1001',(rule['target'],))
   item=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],quantity=2,group=4)])[0]
  s=LocalSession(a,enter_town=True,client_build='dx11_260923');s.role='game';s.phase='town_ready';s.item_test=True
  return path,a,s,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
 def dump(self,path):
  with contextlib.closing(sqlite3.connect(path))as db:return tuple(db.iterdump())
 def test_fresh_and_replay_keep_current_skills_without_auto_entry_or_repeat_stage(self):
  path,a,s,payload=self.case();replies=s.handle(Event(0x202,kind=0x219,payload=payload),7)
  self.assertEqual([e.kind for e in replies],[0x21a,0xd9,0x59f,0x446,0x123,0x55b])
  self.assertEqual(struct.unpack('>ii',replies[2].payload),(0,2));self.assertEqual(replies[3].payload[:2],struct.pack('>H',a.character()['unit_class']))
  first=self.dump(path);again=s.handle(Event(0x202,kind=0x219,payload=payload),7)
  self.assertEqual([e.kind for e in again],[0x21a,0xd9,0x446,0x123,0x55b]);self.assertEqual(self.dump(path),first)
  self.assertFalse(any(e.kind==0x29f for e in replies+again));self.assertEqual(s.phase,'town_ready')
 def test_notification_failure_rolls_back_item_class_Artifact_and_receipt(self):
  path,a,s,payload=self.case();before=self.dump(path)
  with patch('els_server.protocol.career_messages.current_skill_notices',side_effect=RuntimeError('owned precommit fault')):
   with self.assertRaisesRegex(RuntimeError,'owned precommit fault'):s.handle(Event(0x202,kind=0x219,payload=payload),8)
  self.assertEqual(self.dump(path),before);self.assertFalse(a.character()['master'])
  self.assertEqual(s.handle(Event(0x202,kind=0x219,payload=payload),8)[0].payload[:4],bytes(4))
 def test_conflicting_retry_cannot_consume_or_emit_transition(self):
  path,a,s,payload=self.case();s.handle(Event(0x202,kind=0x219,payload=payload),9);before=self.dump(path)
  other=bytearray(payload);other[7]^=1
  reply=s.handle(Event(0x202,kind=0x219,payload=bytes(other)),9)
  self.assertEqual(len(reply),1);self.assertNotEqual(reply[0].payload[:4],bytes(4));self.assertEqual(self.dump(path),before)
 def test_invalid_solo_and_party_admission_show_native_refusal_not_empty_unknown_code(self):
  for kind,ack in((0x37f,0x380),(0x382,0x383)):
   s=LocalSession(None,True,True,'dx11_260923');s.role='game';s.phase='town_ready'
   reply=s.handle(Event(0x202,kind=kind,payload=b'\0'*37))
   self.assertEqual(len(reply),1);self.assertEqual(reply[0].kind,ack);self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],2);self.assertEqual(s.phase,'town_ready')
 def test_all_315_legal_native_snapshots_preserve_current_ranks_seals_Artifact(self):
  count=0
  from els_server.game_data import client_data
  for klass,meta in CLASSES.items():
   stage=meta['stage'];states=[(False,False)]if stage<2 else[(False,False),(True,False)]if stage==2 else[(True,False),(True,True)]
   for tc,master in states:
    role=dict(uid=1001,name='OwnRole',unit_type=client_data().unit(klass)['unitType'],unit_class=klass,level=99,transcendence=tc,master=master,revision=1,skill_seal_groups=tuple(range(1,12)),artifact=None)
    if master:role['artifact']=dict(template=role['unit_type'],evolution=1,level=1,experience=0,potentials=[0]*4)
    events=current_skill_notices(role,default_slots(role));self.assertEqual([e.kind for e in events],[0x446]+([0x123]if master else[]));wire=events[0].payload
    self.assertEqual(struct.unpack_from('>Hii',wire),(klass,0,0));n=struct.unpack_from('>I',wire,10)[0];offset=14;ranks={}
    for _ in range(n):
     identity,rank,unused,byte=struct.unpack_from('>iBiB',wire,offset);self.assertNotIn(identity,ranks);ranks[identity]=rank;self.assertEqual((unused,byte),(0,0));offset+=10
    self.assertEqual(ranks,learned_skills(role));n=struct.unpack_from('>I',wire,offset)[0];offset+=4
    seals=list(struct.unpack_from('>'+str(n)+'i',wire,offset));offset+=n*4;self.assertEqual(seals,list(unsealed_skills(role)))
    t,e,l,xp,potentials=struct.unpack_from('>iiiQI',wire,offset);offset+=24
    self.assertEqual((t,e,l,xp,potentials),(role['unit_type'],1,1,0,4)if master else(0,0,0,0,0));offset+=potentials*4;self.assertEqual(offset,len(wire));count+=1
  self.assertEqual(count,315)


if __name__=='__main__':unittest.main()
