"""All route totals, stable receipts and real SQLite rollback/cold reads."""
import source
from source import HERE,BASE,CHANNEL,CANDIDATE
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import copy,hashlib,json,sqlite3,tempfile,uuid
from els_server.domain import normal_fatigue_rules as rules
from els_server.storage import normal_fatigue as storage
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.domain.dungeon_routes import route_catalog

data=rules.policy();old=json.loads((BASE/'els_server/data/normal_fatigue.json').read_bytes())
web={str(x['map']):x for x in json.loads((HERE/'website-audit.json').read_bytes())['rows']}
checks=[];paid=[];exempt=[];fixed=[];stages_checked=0
for mid,row in data['routes'].items():
 assert rules.route(int(mid))is row
 graph=route_catalog()._data['graphs'][row['source'].lower()]
 if row['cost']==0:
  assert row==old['routes'][mid];exempt.append(int(mid));continue
 assert set(row['stage_costs'])==set(graph['stages'])
 assert sum(row['stage_costs'].values())==web[mid]['total']
 context=dict(epoch=str(uuid.uuid4()),reward_run=str(uuid.uuid4()),owner=1001,dungeon=int(mid),graph_sha256=row['graph_sha256'])
 for st in map(int,graph['stages']):
  c=dict(context,stage=st,part=0,visits=1);stable,amount=rules.debit(row,c)
  for part in graph['stages'][str(st)]['parts']:
   for visits in (1,2,17):
    assert rules.debit(row,dict(c,part=int(part),visits=visits))==(stable,amount)
  assert amount==row['stage_costs'][str(st)];stages_checked+=1
  if row['basis']=='cobodex_missing_field_total_reference_local_rule':
   expected={k:c[k] for k in ('epoch','reward_run','owner','dungeon','stage','graph_sha256')}
   expected['scope']='cobodex-total-once-per-original-stage';assert stable==expected
 if row['basis']=='current_client_explicit':fixed.append(int(mid))
 paid.append(int(mid))
assert len(paid)==223 and len(exempt)==37 and len(fixed)==91
assert rules.route(35600)['stage_costs']=={'0':16,'1':16,'2':16}
assert rules.route(35300)['stage_costs']=={'0':50,'1':50,'2':50}
checks+=['all260-routes-223-public-totals-and37-existing-zero-cost-preserved','all-original-parts-and-revisits-stable','132-existing-receipt-keys-preserved','35600-total48-and35300-total150']
with tempfile.TemporaryDirectory(prefix='owned-fatigue-')as tmp:
 path=Path(tmp)/'game.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters();account.get_inventory_snapshot()
 owner=1001;owner2=Characters(path,1).create('FatigueQA',1,'owned-fatigue')['uid']
 epoch=str(uuid.uuid4());r=rules.route(35600)
 def dump():
  with closing(sqlite3.connect(path))as db:return list(db.iterdump())
 def apply(db,who,stage,part=0,visits=1):
  c=dict(epoch=epoch,reward_run=epoch,owner=who,dungeon=35600,stage=stage,part=part,visits=visits,graph_sha256=r['graph_sha256']);stable,amount=rules.debit(r,c)
  op='fatigue-stage:'+hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  return storage._apply(db,path,who,1,op,'stage',stable,data['sha256'],amount,prepare=lambda writer:storage._writer(writer,path))
 before=dump()
 try:
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');apply(db,owner,0)
   with patch.object(storage,'encode_event',side_effect=ValueError('owned second member encoding failure')):apply(db,owner2,0)
 except ValueError:pass
 else:raise AssertionError('encoding failure not injected')
 assert dump()==before
 for st in range(3):
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE')
   for who in(owner,owner2):assert not apply(db,who,st)['replayed']
  before=dump()
  with closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE')
   for who in(owner,owner2):assert apply(db,who,st,part=99,visits=17)['replayed']
  assert dump()==before
 with closing(sqlite3.connect(path))as db:
  assert all(storage.snapshot(db,who,1)['current']==4752 for who in(owner,owner2))
  assert db.execute('SELECT COUNT(*) FROM normal_fatigue_operations').fetchone()==(6,)
 checks+=['two-real-owners-total48-cold-read','second-member-encoding-failure-rolls-back-all','replay-no-extra-debit-or-ledger']
assert not path.exists()
out=dict(ok=True,channel=CHANNEL,checks=checks,routes=260,paid_routes=len(paid),fixed_paid_routes=len(fixed),zero_cost_routes=len(exempt),stages_checked=stages_checked,temporary_save_removed=True,natural_GUI=False)
(HERE/f'qa-rules-{CHANNEL}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
