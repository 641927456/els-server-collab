"""Real shared opening transactions for every approved box and rule branch."""
from bootstrap import *
from contextlib import closing
from collections import Counter
import hashlib,sqlite3,struct,tempfile,time,traceback
from els_server.domain.retained_box_openings import boxes,preview_outputs,selected_outputs,branches_for
from els_server.domain.equipment_requirements import catalog as classes
from els_server.storage.game_schema import prepare as initialize
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.storage.fixed_cubes import open_cube
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.protocol.ice_messages import preview_ack

def totals(rows):
 result=Counter()
 for r in rows:result[r['template']]+=r['count']
 return result
def rewards(events):
 raw=events[-1].payload;n=struct.unpack_from('>I',raw,12)[0]
 return Counter(dict(struct.unpack_from('>ii',raw,16+8*j)for j in range(n)))
def wire(uid,count=2,side=0):return struct.pack('>QBBBIi',uid,0,side,0,0,count)
def seed(db,owner,t,count):
 rows=load_items(db,owner);group=TEMPLATE_BAG_GROUPS[t];slot=next(i for i in range(1000)if not any((r['group'],r['slot'])==(group,i)for r in rows))
 uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0];db.execute('UPDATE inventory_sequence SET next_uid=next_uid+1 WHERE id=1')
 db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(uid,owner,t,VERIFIED_TEMPLATES[t],count,group,slot));return uid
def dump(path):
 with closing(sqlite3.connect(path))as db:return tuple(db.iterdump())
def items(path,owner):
 with closing(sqlite3.connect(path))as db:return load_items(db,owner)

def main():
 rows=[];failed=[];folder=OUT/'full-stack/native-inputs';folder.mkdir(parents=True,exist_ok=True);class_rows=classes()[0];start=time.monotonic()
 reused={}
 previous=OUT/'local-matrix-affected.json'
 if previous.exists():reused={(r['template'],r['branch']):r for r in json.loads(previous.read_bytes())['cases']}
 requested=set(map(int,sys.argv[1:]))if len(sys.argv)>1 else None
 with tempfile.TemporaryDirectory(prefix='local-box-matrix-',dir=OUT)as temporary:
  tmp=Path(temporary);clean=tmp/'clean.sqlite3';initialize(clean);owner=Characters(clean).create('LocalRuleQA',1,'local-rule-qa')['uid'];account=LocalAccount(LocalState(clean,owner));account.enable_characters();account.get_inventory_snapshot()
  for t,row in boxes().items():
   if not row.get('branches')or requested is not None and t not in requested:continue
   for n,branch in enumerate(row['branches']):
    if(t,n)in reused:rows.append(reused[t,n]);continue
    try:
     cls=next(c for c,facts in class_rows.items()if('classes'not in branch or c in branch['classes'])and('families'not in branch or facts['family']in branch['families']));family=class_rows[cls]['family'];side=branch.get('active_unit',0);char=dict(unit_class=cls,unit_type=family,active_unit=side,level=99)
     assert len([b for b in branches_for(t,char)if b['key']==branch['key']])==1,(t,cls,side,branch['key'])
     entries=preview_outputs(t,char,(branch['key'],));preview=preview_ack(0,t,selection_count=0,entries=[(o['template'],0,o['quantity'])for o in entries]);assert entries
     path=tmp/'case.sqlite3'
     with closing(sqlite3.connect(clean))as source,closing(sqlite3.connect(path))as dest:source.backup(dest)
     with closing(sqlite3.connect(path))as db,db:
      db.execute('UPDATE characters SET level=99,unit_type=?,unit_class=?,transcendence=1 WHERE uid=?',(family,cls,owner))
      quantity=min(3,TEMPLATE_MAX_STACKS[t]);openings=min(2,quantity)
      uid=seed(db,owner,t,quantity)
      if branch['key']:seed(db,owner,branch['key'],branch['key_count']*openings)
      if family==10:
       from els_server.storage.luciel_state import ensure_active
       ensure_active(db)
       db.execute('INSERT OR REPLACE INTO luciel_active_states VALUES(?,?,0)',(owner,side))
     def prepare(db):require_owner(db,owner,1);require_active_character(db,owner)
     before=totals(items(path,owner));rolls=[]
     def roll(bound):rolls.append(bound);return 0
     payload=wire(uid,count=openings,side=side);events=open_cube(path,owner,t,payload,'local-matrix',roll,account_id=1,prepare=prepare)
     selected=selected_outputs(branch,0 if branch['random']else None);expected=Counter()
     for o in selected:expected[o['template']]+=openings*o['quantity']
     assert rewards(events)==expected,(t,n,rewards(events),expected)
     after=totals(items(path,owner));delta=Counter(expected);delta[t]-=openings
     if branch['key']:delta[branch['key']]-=branch['key_count']*openings
     assert {q:after[q]-before[q]for q in set(after)|set(before)if after[q]!=before[q]}=={q:v for q,v in delta.items()if v},(t,n,'inventory delta')
     assert len(rolls)==(openings if branch['random']else 0)
     saved=dump(path);retry=open_cube(path,owner,t,payload,'local-matrix',lambda _:(_ for _ in()).throw(AssertionError('Replay RNG')),account_id=1,prepare=prepare);assert rewards(retry)=={}and dump(path)==saved
     case=dict(template=t,family=family,unit_class=cls,active_unit=side,branch=n,key=branch['key'],preview=preview.payload.hex(),events=[dict(kind=e.kind,payload=e.payload.hex())for e in events])
     target=folder/f'{t}-{n}.json';target.write_text(json.dumps(case),'utf8')
     rows.append(dict(template=t,branch=n,family=family,unit_class=cls,active_unit=side,key=branch['key'],draws=len(rolls),reward_entries=len(expected),preview_entries=len(entries),native_input_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    except Exception:failed.append(dict(template=t,branch=n,error=traceback.format_exc()))
   print(json.dumps(dict(template=t,passed=sum(r['template']==t for r in rows),failures=sum(r['template']==t for r in failed),elapsed=round(time.monotonic()-start,1))),flush=True)
 report=dict(ok=not failed,passed=len(rows),boxes=len({r['template']for r in rows}),failures=failed,cases=rows,own_isolated_saves=True,player_save_access=False)
 (OUT/('local-matrix-affected.json'if requested else'local-matrix.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(dict(ok=report['ok'],passed=len(rows),failures=len(failed))))
 raise SystemExit(bool(failed))
if __name__=='__main__':main()
