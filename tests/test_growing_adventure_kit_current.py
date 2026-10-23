"""Portable growing-kit transaction fixture; no original image or GUI."""
import hashlib,json,sqlite3,struct,tempfile,time,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.domain.growing_adventure_kit import outputs_for,source
from els_server.domain.equipment_requirements import catalog as classes
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items,InventoryFull
from els_server.storage import fixed_cubes
from els_server.storage.item_instances import remove
from els_server.storage.bag_capacity import allowances
ROWS=[]
def wire(uid,choices=(),option=0):return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',x)for x in choices)+struct.pack('>i',option)
class GrowingAdventureKitTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='growing-kit-risk-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3';root=LocalAccount(LocalState(self.path));root.enable_characters()
  self.uid=root.characters.create('GrowingOwner',1,'growing-owner')['uid'];self.other=root.characters.create('GrowingOther',5,'growing-other')['uid'];self.account=root.for_character(self.uid)
  self.account.get_inventory_snapshot();root.for_character(self.other).get_inventory_snapshot()
 def items(self,uid=None):
  with closing(sqlite3.connect(self.path))as db:return load_items(db,self.uid if uid is None else uid)
 def grant(self,t,n=1):
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)],self.uid)
 def snapshot(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def open(self,item,op='growing',**kw):return fixed_cubes.open_cube(self.path,self.uid,168889,wire(item['uid'],**kw),op)
 def reject(self,fn,error=ValueError):
  before=self.snapshot()
  with self.assertRaises(error):fn()
  self.assertEqual(self.snapshot(),before)
 def test_current_receipt_pending_finalized_class_and_cold(self):
  box=self.grant(168889,2)[0];before_uids={i['uid']for i in self.items()};foreign=self.items(self.other);balances=self.account.get_reward_balances();answer=self.open(box)
  self.assertEqual(struct.unpack_from('>iiiI',answer[-1].payload),(0,0,0,5))
  new=[i for i in self.items()if i['uid']not in before_uids];self.assertEqual(len(new),5);self.assertEqual({i['template']for i in new},{r['template']for r in outputs_for(1)})
  first=new[0]
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE inventory_items SET slot=30 WHERE uid=?',(first['uid'],))
  occupant=self.grant(60100)[0];self.assertEqual(occupant['slot'],first['slot'])
  before=self.snapshot();retry=self.open(box);self.assertEqual(struct.unpack_from('>iiiI',retry[-1].payload),(0,0,0,0));self.assertEqual(self.snapshot(),before)
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');remove(db,self.uid,first)
  before=self.snapshot();self.open(box);self.assertEqual(self.snapshot(),before);self.assertFalse(any(i['uid']==first['uid']for i in self.items()))
  for column in ('requested_at','finalized_at'):
   with closing(sqlite3.connect(self.path))as db,db:self.assertEqual(db.execute(f'UPDATE character_lifecycle SET {column}=? WHERE uid=?',(int(time.time()),self.uid)).rowcount,1)
   self.reject(lambda:self.open(box));self.reject(lambda:self.open(box,'new-'+column))
   with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE character_lifecycle SET requested_at=0,finalized_at=0 WHERE uid=?',(self.uid,))
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET unit_class=999999 WHERE uid=?',(self.uid,))
  self.reject(lambda:self.open(box));self.reject(lambda:self.open(box,'unknown-class'))
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET unit_class=1 WHERE uid=?',(self.uid,))
  before=self.snapshot();self.open(box);self.assertEqual(self.snapshot(),before)
  cold=LocalAccount(LocalState(self.path,self.uid));cold.enable_characters();self.assertEqual(cold.get_inventory_snapshot()['items'],self.items());self.assertEqual(self.items(self.other),foreign);self.assertEqual(self.account.get_reward_balances(),dict(balances,revision=balances['revision']+1))
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  ROWS.append(dict(case='new-growing-current-UID-and-receipt-active-current-class-cold',outputs=5,new_or_old_pending_finalized_rejected=True,zero_repeat=True,foreign_ED_preserved=True))
 def test_partial_capacity_and_late_encoder_rollback(self):
  box=self.grant(168889)[0]
  with closing(sqlite3.connect(self.path))as db:cap=allowances(db,self.uid)[1]
  occupied=sum(i['group']==1 for i in self.items());fillers=self.grant(60100,cap-4-occupied)
  self.reject(lambda:self.open(box,'four-free'),InventoryFull)
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');remove(db,self.uid,fillers[0])
  with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('private-growing-five-encoder')):self.reject(lambda:self.open(box,'late-encoder'))
  answer=self.open(box,'exact-five-free');self.assertEqual(struct.unpack_from('>iiiI',answer[-1].payload),(0,0,0,5));self.assertEqual(sum(i['group']==1 for i in self.items()),cap)
  ROWS.append(dict(case='new-growing-four-free-rollback-five-free-success-late-frame-encoder-rollback',SQL_atomic=True,output_slots=5))
 def test_choice_foreign_source_lock_expiry_and_full_class_aliases(self):
  box=self.grant(168889)[0]
  self.reject(lambda:self.open(box,'client-choice',choices=(11030180,)))
  self.reject(lambda:self.open(box,'client-group',option=100168903))
  self.reject(lambda:fixed_cubes.open_cube(self.path,self.other,168889,wire(box['uid']),'foreign-source'))
  from els_server.storage.item_locks import assign as lock,forget as unlock
  from els_server.storage.item_expiration import assign as expire
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');lock(db,self.uid,box['uid'],int(time.time())+300)
  self.reject(lambda:self.open(box,'locked'))
  with closing(sqlite3.connect(self.path))as db,db:db.execute('BEGIN IMMEDIATE');unlock(db,box['uid']);expire(db,self.uid,box['uid'],int(time.time())-1)
  self.reject(lambda:self.open(box,'expired'))
  current=classes()[0]
  for c,meta in current.items():
   out=outputs_for(c);base=next(r for r in source()['kits']if r['current_family']==meta['family']);self.assertEqual({r['template']for r in out},{base['weapon_template'],*base['ordinary_armor_templates']});self.assertEqual(len(out),5)
  ROWS.append(dict(case='new-growing-no-client-class-choice-foreign-lock-expiry-and-current-career-aliases',SQL_zero=True,source_class_aliases=len(current),family_count=15,alias_layer='static current authoritative class map, not natural career journeys'))
if __name__=='__main__':unittest.main()
