from bootstrap import *
from verify_local_rules import *
from unittest.mock import patch
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.bag_capacity import expand,PRODUCT_GROUPS
import uuid

rows=[];failures=[];class_rows=classes()[0];folder=OUT/'full-stack/native-inputs'
previous=OUT/'session-and-large-initial.json'
if previous.exists():rows=json.loads(previous.read_bytes())['cases']
with tempfile.TemporaryDirectory(prefix='local-session-',dir=OUT)as temporary:
 tmp=Path(temporary);clean=tmp/'clean.sqlite3';initialize(clean);owner=Characters(clean).create('SessionQA',1,'session-qa')['uid'];account=LocalAccount(LocalState(clean,owner));account.enable_characters();account.get_inventory_snapshot()
 for t,row in boxes().items():
  if not row.get('branches'):continue
  try:
   branch=row['branches'][0];cls=next(c for c,f in class_rows.items()if('classes'not in branch or c in branch['classes'])and('families'not in branch or f['family']in branch['families']));family=class_rows[cls]['family'];side=branch.get('active_unit',0);path=tmp/'case.sqlite3'
   with closing(sqlite3.connect(clean))as source,closing(sqlite3.connect(path))as dest:source.backup(dest)
   with closing(sqlite3.connect(path))as db,db:
    db.execute('UPDATE characters SET level=99,unit_type=?,unit_class=? WHERE uid=?',(family,cls,owner));db.execute('DELETE FROM skill_slots WHERE uid=?',(owner,));uid=seed(db,owner,t,min(3,TEMPLATE_MAX_STACKS[t]))
    if branch['key']:seed(db,owner,branch['key'],branch['key_count']*2)
    if t==108902:
     from els_server.storage.item_locks import assign
     assign(db,owner,uid,int(time.time())+3600);uid=seed(db,owner,t,3)
   a=LocalAccount(LocalState(path,owner));a.enable_characters();s=LocalSession(a,item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_dungeon=True,enter_town=True,client_build='dx11_260923');s.role='game';s.phase='town_ready';s.active_map=1500
   def prepare(db):require_owner(db,owner,1);require_active_character(db,owner)
   key=next((int(k)for k,v in row['key_aliases'].items()if v==branch['key']),branch['key']);p=struct.pack('>iIiBB',t,1,key,0,side)
   with patch('els_server.domain.tenebros_capacity_flow.selected',return_value=(path,owner,1,prepare)):
    answer=s._handle(Event(0x202,performers=(0,),kind=0x559,payload=p),11)
    assert len(answer)==1 and answer[0].kind==0x55a and struct.unpack_from('>i',answer[0].payload)[0]==0,(t,answer)
    assert s.fixed_cube_preview_template==t
    count=min(2,TEMPLATE_MAX_STACKS[t]);used=s._handle(Event(0x202,performers=(0,),kind=0x196,payload=wire(uid,count,side)),12)
    assert used and used[-1].kind==0x197 and struct.unpack_from('>i',used[-1].payload)[0]==0,(t,used)
   rows.append(dict(template=t,key=key,session_preview=True,session_openings=count,selected_context_fixture=True))
  except Exception:failures.append(dict(template=t,error=traceback.format_exc()))
 # Full pool batches, even if some members were covered by another box earlier.
 for t in(85003720,160773):
  try:
   row=boxes()[t];branch=max(row['branches'],key=lambda b:len(b['outputs']))
   if any(r['template']==t and r.get('whole_pool_count')==len(branch['outputs'])for r in rows):continue
   cls=next(c for c,f in class_rows.items()if('classes'not in branch or c in branch['classes'])and('families'not in branch or f['family']in branch['families']));family=class_rows[cls]['family'];side=branch.get('active_unit',0);path=tmp/'large.sqlite3'
   with closing(sqlite3.connect(clean))as source,closing(sqlite3.connect(path))as dest:source.backup(dest)
   count=len(branch['outputs'])
   with closing(sqlite3.connect(path))as db,db:
    db.execute('UPDATE characters SET level=99,unit_type=?,unit_class=? WHERE uid=?',(family,cls,owner))
    for product in PRODUCT_GROUPS:expand(db,owner,product,36);expand(db,owner,product,8)
    uid=seed(db,owner,t,count)
    if branch['key']:seed(db,owner,branch['key'],count*branch['key_count'])
   def prepare(db):require_owner(db,owner,1);require_active_character(db,owner)
   rolls=[];at=0
   for o in branch['outputs']:rolls.append(at);at+=o['weight']
   queue=iter(rolls);events=open_cube(path,owner,t,wire(uid,count,side),'whole-pool',lambda _:next(queue),account_id=1,prepare=prepare)
   assert len(rewards(events))==count and rewards(events)=={o['template']:o['quantity']for o in branch['outputs']}
   char=dict(unit_type=family,unit_class=cls,active_unit=side,level=99);entries=preview_outputs(t,char,(branch['key'],));p=preview_ack(0,t,entries=[(o['template'],0,o['quantity'])for o in entries]);case=dict(template=t,family=family,preview=p.payload.hex(),events=[dict(kind=e.kind,payload=e.payload.hex())for e in events]);target=folder/f'{t}-whole-pool-{count}.json';target.write_text(json.dumps(case),'utf8');rows.append(dict(template=t,whole_pool_count=count,native_input_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
  except Exception:failures.append(dict(template=t,full_pool=True,error=traceback.format_exc()))
 # Both newly admitted fishing parts are ordinary owned gear with native durability.
 for template,roll,slot in((135930,1,1),(135932,3,2)):
  if any(r['template']==template and r.get('gear_wear')for r in rows):continue
  try:
   path=tmp/'fish.sqlite3'
   with closing(sqlite3.connect(clean))as source,closing(sqlite3.connect(path))as dest:source.backup(dest)
   with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,));db.execute('UPDATE location SET town=1500 WHERE uid=?',(owner,));uid=seed(db,owner,135956,1)
   def prepare(db):require_owner(db,owner,1);require_active_character(db,owner)
   events=open_cube(path,owner,135956,wire(uid,1),'fish-part',lambda _:roll,account_id=1,prepare=prepare);item=next(i for i in items(path,owner)if i['template']==template);assert item['durability']==10000 and item['count']==1
   from els_server.storage.fishing_equipment import move
   payload=struct.pack('>BiBiB',21,item['slot'],22,slot,0);reply=move(path,payload,owner,account_id=1,session_id=str(uuid.uuid4()),sequence=1,expected_town=1500)
   cold=next(i for i in items(path,owner)if i['uid']==item['uid']);assert(cold['group'],cold['slot'],cold['durability'])==(22,slot,10000);rows.append(dict(template=template,gear_wear=True,durability=cold['durability'],slot=slot))
  except Exception:failures.append(dict(template=template,fishing=True,error=traceback.format_exc()))
report=dict(ok=not failures,cases=rows,passed=len(rows),failures=failures,own_isolated_saves=True,session_dispatch='LocalSession._handle',selected_context_fixture=True,live_game=False,natural_GUI=False)
(OUT/'session-and-large-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(dict(ok=report['ok'],passed=len(rows),failures=failures),ensure_ascii=False));raise SystemExit(not report['ok'])
