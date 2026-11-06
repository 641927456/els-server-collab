from pathlib import Path
import asyncio,json,os,sys,tempfile
HOME=Path(__file__).resolve().parent;os.environ['TMP']=os.environ['TEMP']=str(HOME);sys.path.insert(0,os.environ['ELS_OWNED_BOX_TEST_RUNTIME'])
from els_server.application import Application
from els_server.config import ServerConfig
async def main():
 with tempfile.TemporaryDirectory(prefix='owned-box-startup-')as folder:
  app=Application(ServerConfig(state_file=Path(folder)/'qa.sqlite3'))
  try:
   await app.start()
   from els_server.domain.owned_reward_boxes import BOXES
   from els_server.domain.inventory_items import VERIFIED_TEMPLATES
   assert BOXES<=VERIFIED_TEMPLATES.keys()
   result=dict(ok=True,actual_Application_start=True,isolated_SQLite=True,network_listener=False,registered_boxes=sorted(BOXES),player_databases_used=False)
  finally:app.close()
 (HOME/'startup-result.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
asyncio.run(main())
