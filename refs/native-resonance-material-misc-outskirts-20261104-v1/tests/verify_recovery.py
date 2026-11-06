import importlib.abc,importlib.util,json,sys,sqlite3,hashlib
from pathlib import Path
from contextlib import closing
W=Path(__file__).resolve().parent;H=W.parent;R=Path('G:/els');base=R/json.loads((H/'parent.json').read_bytes())['path'];sys.path.insert(0,str(base));mode=sys.argv[1];path=Path(sys.argv[2])
root=H/'candidate'if mode=='write'else W/'recovery'
class Finder(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  p=root/Path(*name.split('.')).with_suffix('.py')
  if p.is_file():return importlib.util.spec_from_file_location(name,p)
sys.meta_path.insert(0,Finder())
from els_server.domain.inventory_items import inventory_payload
from els_server.storage.inventory_state import load_items,grant_items
from els_server.domain.reward_rules import item_plan
templates=(711763,711785,118191,118250)
if mode=='write':
 from els_server.domain.local_session import LocalAccount
 from els_server.storage.local_state import LocalState
 from els_server.domain.raid_reward_items import _issue_source
 a=LocalAccount(LocalState(path));a.enable_characters();a.enable_rewards();a.get_inventory_snapshot()
 with closing(sqlite3.connect(path))as db,db:
  db.execute('BEGIN IMMEDIATE');plan=[item_plan(t,2)for t in templates];cap=_issue_source(db,a.uid,'owned-forward-reader-fixture','ordinary',dict(owned_fixture=True),plan,lambda d:True);grant_items(db,plan,a.uid,raid_reward_source=cap)
 print('Owned new-material fixture written')
else:
 with closing(sqlite3.connect(path))as db:
  items=load_items(db,1001);assert{t:sum(i['count']for i in items if i['template']==t)for t in templates}==dict.fromkeys(templates,2);inventory_payload(items)
  db.execute('BEGIN IMMEDIATE')
  for t in templates:
   try:grant_items(db,[item_plan(t,1)],1001)
   except ValueError:pass
   else:raise AssertionError('Recovery reopened generic material production')
  db.rollback()
 report=dict(passed=True,previous_producers_with_forward_readers=True,new_material_templates=list(templates),cold_read_and_full_inventory_encode=True,generic_production_closed=True,player_database_restore=False)
 (W/'recovery-reader-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
