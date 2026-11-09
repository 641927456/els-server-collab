"""Owned G-drive SQLite fixtures; no App, Game, players or installation."""
from qa_environment import F
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import json,sqlite3,struct,tempfile,unittest,sys
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import insert,next_uid
from els_server.storage import housing_access as access,housing_rooms as rooms,housing_layouts as layouts,housing_expansions as expansion,shop_state as shop
from els_server.domain.bag_capacity import capacities,wire_limit
from els_server.protocol.housing_layout_messages import REQUEST,LAYOUT,encode,decode
NOW=1900000000
PURCHASE_CALLS=0

class HousingStorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='owned-housing-',dir=F);self.addCleanup(self.tmp.cleanup)
  from els_server.storage.game_schema import prepare
  from els_server.storage.characters import Characters
  self.path=Path(self.tmp.name)/'own.sqlite3';prepare(self.path);roster=Characters(self.path,1)
  self.uid=roster.create('OwnedHouse',1,'owned-create')['uid'];self.a=LocalAccount(LocalState(self.path,self.uid));self.a.enable_characters(characters=roster);self.a.get_inventory_snapshot();self.account=self.a.account_id;self.serial=0
  with self.db()as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(self.uid,));db.execute('UPDATE reward_balances SET ed=10000 WHERE uid=?',(self.uid,))
  item=self.stock(713275)
  access.use(self.path,self.uid,self.account,self.body(item), 'owned-first-contract',lambda db:None,now=NOW)
  self.admission='owned-enter';self.generation=rooms.enter(self.path,self.uid,self.account,struct.pack('>Qi3fB',0,26000,0,0,0,1),self.admission,'owned-session',self.a.get_location()['map'],lambda db:None,now=NOW)['generation']
 def db(self):return closing(sqlite3.connect(self.path))
 def dump(self):
  with self.db()as db:return list(db.iterdump())
 def stock(self,t):
  # Explicit existing-item fixture; only purchase() below claims acquisition.
  with self.db()as db,db:return grant_items(db,[dict(template=t,metadata=0,quantity=1,group=4)],self.uid)[0]
 def body(self,item,target=0):return struct.pack('>QQiiIB',item['uid'],target,0,0,0,0)
 def use(self,item,target=0,operation=None,guard=lambda db:None):
  self.serial+=1
  return expansion.use(self.path,self.uid,self.account,self.body(item,target),operation or f'owned-use-{self.serial}',self.generation,self.admission,guard,now=NOW)
 def room(self):return rooms.read(self.path,self.uid,self.account)
 def purchase(self,templates,operation='owned-purchase'):
  global PURCHASE_CALLS
  offers={p['template']:p for p in shop.catalog()};payload=struct.pack('>I',len(templates))+b''.join(struct.pack('>IH',offers[t]['sku'],1)for t in templates)
  shop.purchase(self.path,payload,operation,self.uid)
  PURCHASE_CALLS+=1
  with self.db()as db:return [i for i in load_items(db,self.uid)if i['template']in templates]
 def placed(self,count,floor=0):
  with self.db()as db,db:
   occupied={i['slot']for i in load_items(db,self.uid)if i['group']==25};items=[]
   for n in range(count):
    slot=next(i for i in range(560)if i not in occupied);occupied.add(slot)
    item=dict(uid=next_uid(db),template=570011,metadata=0,group=25,slot=slot,count=1);insert(db,self.uid,item);items.append(item)
  return ([],[(i['uid'],(i['uid'],i['template'],2,(float(n%24*25),100.0,float(n//24*25)),0))for n,i in enumerate(items)],[],0,floor,0)
 def save(self,request,operation='owned-save',guard=lambda db:None):return layouts.save(self.path,self.uid,self.account,encode(REQUEST,request),operation,self.generation,self.admission,guard,now=NOW)
 def test_six_actual_shop_products_50ED_purchase_and_replay(self):
  templates=(136030,136031,136032,136033,136241,136245);items=self.purchase(templates);self.assertEqual(len(items),6)
  with self.db()as db:self.assertEqual(db.execute('SELECT ed FROM reward_balances WHERE uid=?',(self.uid,)).fetchone(),(9700,))
  before=self.dump();self.purchase(templates);self.assertEqual(self.dump(),before)
  self.assertEqual(capacities()[25],560);self.assertEqual(wire_limit(25),560)
 def test_each_stage_uses_matching_contract_once_and_replays_current_state(self):
  items=self.purchase((136030,136031,136032,136033));items.sort(key=lambda i:i['template'])
  for n,item in enumerate(items,1):self.use(item,operation=f'owned-stage-{n}');self.assertEqual(self.room()['layout'],[(0,(n,n))])
  before=self.dump();events=self.use(items[0],operation='owned-stage-1');self.assertEqual(self.dump(),before);self.assertEqual([e.kind for e in events],[0x21a,0x93d,0x946]);self.assertEqual(struct.unpack_from('>i',events[-1].payload)[0],4)
 def test_floor_contract_does_not_require_previous_floor_expansion(self):
  for target in(2,3):self.use(self.stock(136241),target)
  self.assertEqual(self.room()['layout'],[(0,(0,0)),(1,(0,0)),(2,(0,0))])
  item=self.stock(136241);before=self.dump()
  with self.assertRaises(ValueError):self.use(item,3)
  self.assertEqual(self.dump(),before)
 def test_wrong_stage_and_floor_target_preserve_item_and_state(self):
  for t,target in((136033,0),(136030,2),(136241,3)):
   item=self.stock(t);before=self.dump()
   with self.assertRaises(ValueError):self.use(item,target)
   self.assertEqual(self.dump(),before)
 def test_preset_ticket_increases_only_to_four_total(self):
  for n in range(3):self.use(self.stock(136245))
  with self.db()as db:self.assertEqual(expansion.preset_expansions(db,self.uid,self.account),3)
  item=self.stock(136245);before=self.dump()
  with self.assertRaises(ValueError):self.use(item)
  self.assertEqual(self.dump(),before)
 def test_expansion_encoder_failure_rolls_back_debit_schema_and_state(self):
  for t,target in((136030,0),(136241,2),(136245,0)):
   item=self.stock(t);before=self.dump()
   with patch.object(expansion,'encode_event',side_effect=ValueError('owned encoder failure')):
    with self.assertRaises(ValueError):self.use(item,target)
   self.assertEqual(self.dump(),before)
 def test_200_owned_furniture_save_cold_and_repeat(self):
  request=self.placed(200);self.save(request)
  with self.db()as db:
   state=layouts.snapshot(db,self.uid,self.account,now=NOW);self.assertEqual(state['layout'],request[:-1]);self.assertEqual(len(state['layout'][1]),200)
   value=rooms.dto(self.a.character(),db=db,account=self.account);self.assertEqual(len(value['0f7'][0][1][1]),200)
  before=self.dump();self.save(request);self.assertEqual(self.dump(),before)
 def test_two_floors_keep_distinct_placements_and_reject_duplicate_UID(self):
  self.use(self.stock(136241),2);first=self.placed(2);self.save(first,'owned-floor0')
  second=self.placed(1,1);self.save(second,'owned-floor1')
  with self.db()as db:self.assertEqual(set(layouts.states(db,self.uid,self.account,now=NOW)),{0,1})
  before=self.dump();duplicate=(*first[:4],1,0)
  with self.assertRaises(ValueError):self.save(duplicate,'owned-duplicate')
  self.assertEqual(self.dump(),before)
 def test_known_v1_floor0_ctor_form_survives_and_is_not_rewritten(self):
  request=self.placed(1);legacy=(*request[:4],-1)
  with self.db()as db,db:
   db.execute('CREATE TABLE character_housing_layouts_v1 (owner INTEGER PRIMARY KEY,account_id INTEGER,version INTEGER,payload BLOB,revision INTEGER,updated_at INTEGER)')
   db.execute('INSERT INTO character_housing_layouts_v1 VALUES (?,?,1,?,1,?)',(self.uid,self.account,encode(LAYOUT,legacy),NOW))
  before=self.dump()
  with self.db()as db:self.assertEqual(layouts.snapshot(db,self.uid,self.account,now=NOW)['layout'],request[:-1])
  self.assertEqual(self.dump(),before);self.save(request)
  with self.db()as db:self.assertEqual(db.execute('SELECT payload FROM character_housing_layouts_v1').fetchone()[0],encode(LAYOUT,legacy))
 def progress(self,account=None):
  with self.db()as db:return dict(db.execute('SELECT achievement,value FROM native_achievement_progress WHERE account_id=? AND achievement IN (375,376,377,378)',(self.account if account is None else account,)))
 def test_housing_achievement_boundaries_and_repeat_saves_do_not_accumulate(self):
  self.assertEqual(self.progress().get(375),1);request=self.placed(200)
  for count in(49,49,50,100,200):
   self.serial+=1;chosen=(request[0],request[1][:count],*request[2:]);self.save(chosen,f'owned-boundary-{self.serial}')
   self.assertEqual(self.progress()[376],count)
   with self.db()as db:
    done={i for i, in db.execute('SELECT achievement FROM native_achievement_completed WHERE account_id=?',(self.account,))}
   self.assertEqual({376,377,378}&done,{i for i,n in((376,50),(377,100),(378,200))if count>=n})
  self.save(([],[],[],0,0,0),'owned-empty');self.assertEqual(self.progress()[376],200)
 def test_furniture_achievement_and_layout_roll_back_together(self):
  request=self.placed(50);before=self.dump()
  with patch.object(layouts,'encode_event',side_effect=ValueError('owned completion encoding failure')):
   with self.assertRaises(ValueError):self.save(request,'owned-rollback')
  self.assertEqual(self.dump(),before);self.save(request,'owned-rollback');self.assertEqual(self.progress()[376],50)
 def test_housing_progress_is_current_role_max_and_account_isolated(self):
  self.save(self.placed(60),'owned-primary60')
  from els_server.storage.characters import Characters
  from els_server.storage.achievement_profiles import reconcile
  account=self.account;uid=Characters(self.path,account).create('OwnedAlt',1,'owned-alt')['uid']
  other=Characters(self.path,2).create('OwnedForeign',1,'owned-foreign')['uid']
  self.a=self.a.for_character(uid);self.uid=uid;self.admission='owned-alt-enter'
  with self.db()as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
  contract=self.stock(713275);access.use(self.path,uid,account,self.body(contract),'owned-alt-contract',lambda db:None,now=NOW)
  self.generation=rooms.enter(self.path,uid,account,struct.pack('>Qi3fB',0,26000,0,0,0,1),self.admission,'owned-alt-session',self.a.get_location()['map'],lambda db:None,now=NOW)['generation']
  self.save(self.placed(50),'owned-alt50')
  with self.db()as db,db:
   db.execute('BEGIN IMMEDIATE');reconcile(db,account,uid,NOW,condition_types=frozenset((64,65)));reconcile(db,2,other,NOW,condition_types=frozenset((64,65)))
  self.assertEqual(self.progress()[376],60);self.assertEqual(self.progress(2),{})
 def test_all_nine_native_floor_templates_accept_floor_and_reject_wall(self):
  from els_server.domain.furniture_rules import validate_layout,LEGACY_FLOOR_POSITION_TEMPLATES
  for n,t in enumerate(sorted(LEGACY_FLOOR_POSITION_TEMPLATES)):
   item=dict(uid=900001+n,template=t,metadata=0,group=25,slot=n,count=1)
   correct=([(item['uid'],(1,item['uid'],t,0,0,0))],[],[],0,0)
   validate_layout(correct,[item],mutating=True,now=NOW)
   wrong=([(item['uid'],(2,item['uid'],t,0,0,0))],[],[],0,0)
   with self.assertRaises(ValueError):validate_layout(wrong,[item],mutating=True,now=NOW)
   validate_layout(wrong,[item],legacy_floor_locations=True,now=NOW)
   with self.assertRaises(ValueError):validate_layout(wrong,[item],now=NOW)
 def test_legacy_record_floor_must_match_layout(self):
  item=dict(uid=900100,template=570011,metadata=0,group=25,slot=0,count=1)
  from els_server.domain.furniture_rules import validate_layout
  with self.assertRaises(ValueError):validate_layout(([(item['uid'],(2,item['uid'],570011,0,0,1))],[],[],0,0),[item],mutating=True,now=NOW)
 def test_expansion_final_actor_guard_rolls_back_item_and_state(self):
  for t,target in((136030,0),(136241,2),(136245,0)):
   item=self.stock(t);before=self.dump();calls=[]
   def guard(db):
    calls.append(True)
    if len(calls)==2:raise ValueError('owned actor changed at commit')
   with self.assertRaises(ValueError):self.use(item,target,guard=guard)
   self.assertEqual(len(calls),2);self.assertEqual(self.dump(),before)
 def test_six_retained_housing_aliases_are_readable_but_not_grantable(self):
  from els_server.domain.housing_expansion_rules import OWNED_ONLY,SHOP_ITEMS
  from els_server.domain.acquisition_policy import can_acquire
  from els_server.domain.inventory_items import validate_item
  self.assertEqual(len(OWNED_ONLY),6)
  for n,t in enumerate(sorted(OWNED_ONLY)):
   self.assertFalse(can_acquire(t))
   validate_item(dict(uid=900200+n,template=t,metadata=0,group=4,slot=n,count=1))
  for t in SHOP_ITEMS:self.assertTrue(can_acquire(t))
 def test_furniture_slot559_cold_snapshot_and_slot560_rejected(self):
  self.placed(560)
  snapshot=self.a.get_inventory_snapshot()
  self.assertEqual(len([i for i in snapshot['items']if i['group']==25]),560)
  with self.db()as db:
   items=load_items(db,self.uid)
   self.assertEqual(max(i['slot']for i in items if i['group']==25),559)
  before=self.dump()
  from els_server.domain.inventory_items import validate_item
  with self.assertRaises(ValueError):validate_item(dict(uid=900999,template=570011,metadata=0,group=25,slot=560,count=1))
  self.assertEqual(self.dump(),before)
 def test_expansion_locked_sealed_expired_contracts_preserve_state(self):
  from els_server.storage.item_locks import assign as lock
  from els_server.storage.item_seals import assign as seal
  from els_server.storage.item_expiration import assign as expire
  for condition in('locked','sealed','expired'):
   item=self.stock(136030)
   with self.db()as db,db:
    db.execute('BEGIN IMMEDIATE')
    if condition=='locked':lock(db,self.uid,item['uid'],NOW+1)
    elif condition=='sealed':seal(db,self.uid,item['uid'],True,0)
    else:expire(db,self.uid,item['uid'],NOW-1)
   before=self.dump()
   with self.assertRaises(ValueError):self.use(item)
   self.assertEqual(self.dump(),before)
 def test_upper_floor_mat_place_replay_retrieve_and_remove(self):
  from els_server.storage import companion_state,pet_progression,housing_pets
  self.use(self.stock(136241),2);pet_uid=90000001
  with self.db()as db,db:
   companion_state.ensure(db);db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',(pet_uid,self.uid,'pet',1,'OwnHomePet',0))
   pet=companion_state.rows(db,self.uid,'pet')[0];pet.update(step=3,growth=0);pet_progression.save(db,self.uid,pet)
   item=dict(uid=next_uid(db),template=570234,metadata=0,group=25,slot=0,count=1);insert(db,self.uid,item)
  request=([(item['uid'],(1,item['uid'],570234,0,0,1))],[],[],0,1,0);self.save(request,'owned-upper-mat')
  body=struct.pack('>BQ',1,pet_uid)
  def perform(kind,operation,now=NOW):return housing_pets.perform(self.path,self.uid,self.account,kind,body,operation,self.generation,self.admission,lambda db:None,now=now)
  perform(0xa38,'owned-place-upper');before=self.dump();perform(0xa38,'owned-place-upper');self.assertEqual(self.dump(),before)
  with self.db()as db:
   rows=housing_pets.projection(db,self.uid,self.account);self.assertEqual((rows[0][0],rows[0][1],rows[0][3]['uid']),(1,0,pet_uid))
  with self.assertRaises(ValueError):self.save(([],[],[],0,1,0),'owned-remove-busy-mat')
  self.assertEqual(self.dump(),before)
  perform(0xa3a,'owned-retrieve-upper',NOW+100);before=self.dump();perform(0xa3a,'owned-retrieve-upper',NOW+100);self.assertEqual(self.dump(),before)
  with self.db()as db:self.assertEqual(housing_pets.saved(db,self.uid),[]);self.assertEqual(companion_state.rows(db,self.uid,'pet')[0]['growth'],0)
  self.save(([],[],[],0,1,0),'owned-remove-free-mat')
 def preset(self,requested,rename,operation,floor=0,guard=lambda db:None):
  from els_server.storage.housing_presets import save
  from els_server.protocol.housing_preset_messages import REQUEST as SCHEMA
  return save(self.path,self.uid,self.account,encode(SCHEMA,(requested,rename)),operation,self.generation,self.admission,floor,guard,now=NOW)
 def test_presets_capture_rename_overwrite_cold_and_current_replay(self):
  from els_server.storage import housing_presets as presets
  from els_server.protocol.housing_preset_messages import PRESET
  self.use(self.stock(136241),2);request=self.placed(2,1);self.save(request,'owned-layout-for-preset')
  self.use(self.stock(136030),1);first=(0,'Own',1,[],[(0,v[1],v[2],v[3],v[4])for key,v in request[1]])
  answer=self.preset(first,False,'owned-preset-first',floor=1)
  actual=decode(PRESET,answer[0].payload[4:]);self.assertEqual(actual[:3],(0,'Own',1));self.assertEqual(len(actual[4]),2);self.assertEqual(actual[4][0][0],0)
  with self.db()as db:
   before=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(self.uid,)).fetchone();inventory=load_items(db,self.uid)
  renamed=(0,'Renamed',*actual[2:]);answer=self.preset(renamed,True,'owned-preset-rename',floor=1)
  self.assertEqual(decode(PRESET,answer[0].payload[4:]),renamed)
  expected=(0,'Renamed',1,[],[(0,570011,2,(100.0,100.0,0.0),0)])
  answer=self.preset(expected,False,'owned-preset-overwrite',floor=1)
  self.assertEqual(decode(PRESET,answer[0].payload[4:]),expected)
  snapshot=self.dump();answer=self.preset(first,False,'owned-preset-first',floor=1);self.assertEqual(self.dump(),snapshot);self.assertEqual(decode(PRESET,answer[0].payload[4:]),expected)
  with self.db()as db:
   self.assertEqual(presets.snapshot(db,self.uid,self.account)[0]['preset'],expected)
   self.assertEqual(rooms.dto(self.a.character(),db=db,account=self.account)['1c5'],[(0,expected)])
   self.assertEqual(layouts.snapshot(db,self.uid,self.account,now=NOW,floor=1)['layout'],request[:-1])
   self.assertEqual(db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(self.uid,)).fetchone(),before);self.assertEqual(load_items(db,self.uid),inventory)
 def test_preset_allowance_stale_summary_and_atomic_failures(self):
  from els_server.storage import housing_presets as presets
  self.placed(1);row=(0,570011,2,(0.0,100.0,0.0),0)
  first=(0,'Own',0,[],[row]);before=self.dump()
  with self.assertRaises(ValueError):self.preset((1,'Locked',0,[],[row]),False,'owned-locked-slot')
  self.assertEqual(self.dump(),before)
  with patch.object(presets,'encode_event',side_effect=ValueError('owned D38 encoding failure')):
   with self.assertRaises(ValueError):self.preset(first,False,'owned-preset-rollback')
  self.assertEqual(self.dump(),before)
  calls=[]
  def guard(db):
   calls.append(True)
   if len(calls)==2:raise ValueError('owned actor changed before preset commit')
  with self.assertRaises(ValueError):self.preset(first,False,'owned-preset-guard',guard=guard)
  self.assertEqual(self.dump(),before);self.preset(first,False,'owned-preset-rollback')
  before=self.dump()
  with self.assertRaises(ValueError):self.preset((0,'Other',1,[],[row]),True,'owned-preset-stale')
  self.assertEqual(self.dump(),before)
  for forged in((0,'No furniture',0,[],[]),(0,'Excess',0,[],[row,row]),(0,'Stage',1,[],[row])):
   with self.assertRaises(ValueError):self.preset(forged,False,'owned-preset-forged')
   self.assertEqual(self.dump(),before)
  self.use(self.stock(136245));self.preset((1,'Second',0,[],[row]),False,'owned-extra-slot')
  with self.db()as db:self.assertEqual(set(presets.snapshot(db,self.uid,self.account)),{0,1})
 def test_original_nonempty_D37_saves_without_changing_house_layout(self):
  from els_server.protocol.housing_preset_messages import REQUEST as SCHEMA,PRESET
  self.use(self.stock(136241),2);self.placed(1);self.use(self.stock(136030),1)
  payload=bytes.fromhex('00000000000000048498be8b000000010000000000000001000000000008b29b000000020000000042c80000000000000000000000')
  requested,rename=decode(SCHEMA,payload);self.assertFalse(rename)
  self.assertEqual(requested[:3],(0,'预设',1))
  answer=self.preset(requested,rename,'owned-actual-native-D37',floor=1)
  self.assertEqual(decode(PRESET,answer[0].payload[4:]),requested)
  with self.db()as db:self.assertEqual(layouts.states(db,self.uid,self.account,now=NOW),{})
 def test_original_92B_floor_samples_and_malformed_movement(self):
  from els_server.protocol.housing_layout_messages import movement_floor
  samples=('000000000000000045426cce00000000010000320000000000000000000000000000','000000000000000045426cce00000001b701010000320000000000020000000000000001')
  for floor,text in enumerate(samples):self.assertEqual(movement_floor(bytes.fromhex(text)),floor)
  payload=bytes.fromhex(samples[1])
  for bad in(payload[:-1],payload+b'\0',payload[:-4]+struct.pack('>i',3),struct.pack('>f',float('nan'))+payload[4:]):
   with self.assertRaises(ValueError):movement_floor(bad)

if __name__=='__main__':
 version=sys.argv[1];names=sys.argv[2:]
 suite=unittest.TestSuite(HousingStorageTests(name)for name in names)if names else unittest.defaultTestLoader.loadTestsFromTestCase(HousingStorageTests)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 output=F/f'storage-test-result-{version}.json';assert not output.exists()
 output.write_text(json.dumps(dict(ok=result.wasSuccessful(),tests=result.testsRun,names=names,failures=len(result.failures),errors=len(result.errors),production_data=False,Game=False,App=False,natural_acquisition=False,actual_shop_purchase=PURCHASE_CALLS>0,shop_purchase_calls=PURCHASE_CALLS,details=[dict(test=str(test),error=error)for test,error in result.errors+result.failures]),indent=2)+'\n','utf8')
 raise SystemExit(0 if result.wasSuccessful()else 1)
