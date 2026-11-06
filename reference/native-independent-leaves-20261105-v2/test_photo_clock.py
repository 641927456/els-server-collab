"""Original studio camera permission follows native integer-second expiration."""
import bootstrap as env
from pathlib import Path
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,json,sqlite3,sys,tempfile,time
from els_server.domain.local_session import LocalAccount
from els_server.domain.item_expiration import expired
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
source=env.BASE/'els_server/domain/photo_zone_flow.py'if '--baseline'in sys.argv else env.HERE/'source/els_server/domain/photo_zone_flow.py'
spec=importlib.util.spec_from_file_location('els_server.domain.photo_zone_flow',source);flow=importlib.util.module_from_spec(spec);sys.modules[spec.name]=flow;spec.loader.exec_module(flow)
report=dict(passed=False,baseline='--baseline'in sys.argv,cases=[],source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),timed_camera_acquisition_tested=False,production_database_access=False)
with tempfile.TemporaryDirectory(prefix='owned-studio-camera-clock-',dir=env.HERE)as tmp:
 path=Path(tmp)/'own.sqlite3';prepare(path);roster=Characters(path,1);uid=roster.create('OwnCamClock',1,'own-camera-clock')['uid']
 account=LocalAccount(LocalState(path,uid),account_id=1);account.enable_characters(characters=roster);account.get_inventory_snapshot()
 deadline=1900000000
 with closing(sqlite3.connect(path))as db,db:
  db.execute('BEGIN IMMEDIATE');item=grant_items(db,[dict(template=288495,metadata=0,group=4,quantity=1,expires_at=deadline)],uid)[0]
  before=list(db.iterdump())
 for stamp in(deadline-1,deadline,deadline+1):
  with patch.object(flow,'time',SimpleNamespace(time=lambda:stamp+.75)):
   character,items,permission=flow._snapshot(SimpleNamespace(account=account))
  own=next(i for i in items if i['uid']==item['uid']);expected=not expired(own,now=stamp)
  assert permission==(False if report['baseline']and stamp==deadline else expected)
  report['cases'].append(dict(server_second=stamp,permission=permission,shared_expiration_permission=expected))
 with closing(sqlite3.connect(path))as db:assert before==list(db.iterdump())
report.update(passed=True,SQL_unchanged=True,temporary_directory_removed=True)
p=env.HERE/('camera-clock-'+('baseline'if report['baseline']else'fixed')+'-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(report,evidence=str(p))))
