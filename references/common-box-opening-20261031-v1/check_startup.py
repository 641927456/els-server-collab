from pathlib import Path
from contextlib import closing
import asyncio,json,os,sqlite3,sys,tempfile
H=Path(__file__).resolve().parent;R=Path(os.environ.get('ELS_COMMON_BOX_RUNTIME',H/'runtime'))
sys.path.insert(0,str(R));os.environ['TMP']=os.environ['TEMP']=str(H);tempfile.tempdir=str(H)
from els_server.application import Application
from els_server.config import ServerConfig
async def main():
 with tempfile.TemporaryDirectory(prefix='common-box-startup-')as folder:
  app=Application(ServerConfig(state_file=Path(folder)/'qa.sqlite3'))
  try:
   assert app.config.selected2026_pair_file is None and app.activity2026_awards_factory is None
   await app.start()
   from els_server.domain.cubes import catalog
   from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
   targets=json.loads((H/'audit.json').read_text(encoding='utf8'))['missing_without_activity']
   assert set(targets)<=catalog().keys() and set(targets)<=VERIFIED_TEMPLATES.keys()
   with closing(sqlite3.connect(app.config.state_file))as db:
    assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'selected2026%' OR name LIKE 'activity2026%'").fetchall()
   from els_server.domain.activity_2026_rewards import ActivityRewards
   before={t:(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])for t in targets}
   ActivityRewards((R/'els_server/data/selected2026/rewards.json').read_bytes()).register_inventory()
   assert before=={t:(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])for t in targets}
   result=dict(ok=True,actual_Application_start=True,no_activity_factory=True,no_activity_enrollment_tables=True,activity_registration_compatible=True,registered_boxes=targets,network_listener=False,player_databases_used=False)
  finally:app.close()
 (H/'startup-result.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
asyncio.run(main())
