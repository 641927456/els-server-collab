"""Direct storage boundaries for new eligibility; live scenarios cover dispatch."""
from qa_environment import F
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,struct,tempfile,time,traceback
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import npc_trade
from els_server.storage.inventory_state import load_items
from els_server.domain import spa_market
from els_server.domain.consumables import manual_recovery_definitions
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.application import Application
from els_server.config import ServerConfig
report=dict(ok=False,production_database_access=False,checks=[])
def payload():return struct.pack('>BHIiii',0,0,1,710012,1,10196)
async def run():
  app=None
  try:
    with tempfile.TemporaryDirectory(prefix='owned-spa-window-rules-',dir=F)as directory:
        path=Path(directory)/'game.sqlite3'
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=path,
            accounts_file=Path(directory)/'accounts.sqlite3',log_dir=Path(directory)/'logs')
        app=Application(cfg);await app.start()
        with patch.object(spa_market,'clock',return_value=300001):
            for unit,minimum in ((1,10),(13,70),(14,70),(15,99)):
                auth=app.registry.create('ownedrule'+str(unit))
                uid=Characters(path,auth['id']).create('OwnRule'+str(unit),unit,'owned-rule-'+str(unit))['uid']
                LocalState(path,uid).save(1500,0,0,(0.,0.,0.))
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('UPDATE characters SET level=? WHERE uid=?',(minimum-1,uid))
                    db.execute('UPDATE reward_balances SET ed=600000 WHERE uid=?',(uid,))
                def saved():
                    with closing(sqlite3.connect(path))as db:
                        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()
                        receipts=db.execute('SELECT count(*) FROM inventory_action_receipts WHERE owner=?',(uid,)).fetchone()[0]if exists else 0
                        return npc_trade.balances(db,uid),load_items(db,uid),receipts
                before=saved()
                try:npc_trade.purchase(path,uid,1500,payload(),'owned-too-low-'+str(uid))
                except ValueError as error:assert str(error)=='Spa level requirement'
                else:raise AssertionError('Below-minimum level admitted')
                assert saved()==before
                with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE characters SET level=? WHERE uid=?',(minimum,uid))
                result=npc_trade.purchase(path,uid,1500,payload(),'owned-qualified-'+str(uid))
                assert result[0].payload[:4]==bytes(4)
                after=saved();assert after[0]['ed']==580000 and sum(i['count']for i in after[1]if i['template']==710012)==1
                report['checks'].append(dict(unit=unit,minimum=minimum,below_rejected=True,exact_minimum_purchased=True))
            assert 136202 not in VERIFIED_TEMPLATES
            definitions={r['template']:r for r in manual_recovery_definitions()}
            assert definitions[710022]==dict(template=710022,metadata=2,group=6,max_stack=500)
            report.update(ok=True,unqualified_other_spa_food136202_closed=True,original_710022_reader_definition_preserved=True)
        app.close();app=None
  except BaseException:report['failure']=traceback.format_exc()
  finally:
    if app is not None:app.close()
  p=F/('window-rules-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  print(json.dumps(report,ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(run()))
