"""Use actual startup to prove warm definitions precede the first player store."""
import runtime_fixture as h
import asyncio,importlib,json,tempfile,time
from unittest.mock import patch
from els_server.application import Application,LocalAccount
from els_server.config import ServerConfig
TARGETS=(('dungeon_equipment_loot_rules','catalog'),('dungeon_loot_catalog','catalog'),('dungeon_material_loot_catalog','catalog'),('dungeon_source_loot','catalog'),('scene_actor_retirements','finite_sources'),('normal_fatigue_rules','policy'),('formal_npc_hp','policy'),('boss_npc_stats','policy'))
async def main():
 out=dict(ok=False,online_changed=False);seen=[]
 def before_account(*args,**kwargs):
  for mod,name in TARGETS:
   fn=getattr(importlib.import_module('els_server.domain.'+mod),name)
   info=fn.cache_info();assert info.currsize>0,(mod,name,info)
   seen.append(dict(module=mod,function=name,cache=info._asdict()))
  return LocalAccount(*args,**kwargs)
 c=h.f.FriendsTests();tick=time.perf_counter()
 with patch('els_server.application.LocalAccount',side_effect=before_account):await c.asyncSetUp()
 try:
  assert len(seen)==len(TARGETS)
  out.update(startup_ms=(time.perf_counter()-tick)*1000,ready_before_player_store=seen)
 finally:
  await c.asyncTearDown();out.update(own_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 with tempfile.TemporaryDirectory(dir=h.H)as name:
  root=h.Path(name);cert=h.Path(h.os.environ['ELS_TEST_CERT_DIR'])
  app=Application(ServerConfig(mode='friends',port=0,state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',tls_cert=cert/'server-cert.pem',tls_key=cert/'server-key.pem'))
  try:
   with patch('els_server.domain.normal_fatigue_rules.policy',side_effect=ValueError('owned immutable rule mismatch'))as policy,patch('els_server.application.LocalAccount',wraps=LocalAccount)as account:
    try:await app.start()
    except ValueError as error:assert str(error)=='owned immutable rule mismatch'
    else:raise AssertionError('Invalid static rule accepted')
    policy.assert_called_once_with();account.assert_not_called()
   assert not(root/'game.sqlite3').exists()and not(root/'accounts.sqlite3').exists()
  finally:app.close()
 assert not root.exists()
 out.update(ok=True,invalid_catalog_rejected_before_player_account=True,no_player_databases_created=True,failure_runtime_removed=True)
 dest=h.H/'startup-validation.json';assert not dest.exists();dest.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
asyncio.run(main())
