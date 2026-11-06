import runtime_fixture as h
import asyncio,importlib,json,tempfile,time
from unittest.mock import patch
from els_server.application import Application,LocalAccount
from els_server.config import ServerConfig
from els_server.game_data import client_data
from els_server.domain.title_economy import dungeon_type,dungeon_types

async def main():
 manifest=json.loads((h.H/'candidate-manifest.json').read_bytes());ready=[];seen=[];tick=time.perf_counter()
 def before_account(*args,**kwargs):
  for mod,name,*params in manifest['extra_static_calls']:
   module=importlib.import_module('els_server.domain.'+mod)
   if name:
    fn=getattr(module,name);info=fn.cache_info();assert info.currsize>0,(mod,name)
    before=info.misses;fn(*params);assert fn.cache_info().misses==before,(mod,name,params)
   ready.append((mod,name,params))
  assert dungeon_types.cache_info().currsize==1
  from els_server.domain.formal_npc_hp import policy,ordinary_dungeon,initialization_factor
  for fn in (ordinary_dungeon,initialization_factor):
   before=fn.cache_info().misses
   for mid in map(int,policy()['maps']):fn(mid)
   assert fn.cache_info().misses==before
  seen.append('before-player-store')
  return LocalAccount(*args,**kwargs)
 c=h.f.FriendsTests()
 with patch('els_server.application.LocalAccount',side_effect=before_account):await c.asyncSetUp()
 out=dict(ok=False,startup_ms=(time.perf_counter()-tick)*1000,prepared_entries=len(ready),before_player_store=seen==['before-player-store'])
 try:
  data=client_data()
  with data.connect()as db:expected={mid:json.loads(raw).get('m_eDungeonType',0)for mid,raw in db.execute('SELECT id,definition FROM dungeons')}
  assert len(expected)==740
  with patch.object(data,'connect',side_effect=AssertionError('Warm type lookup opened catalog')):
   tick=time.perf_counter()
   assert {mid:dungeon_type(mid)for mid in expected}==expected
   out['all_740_type_lookup_ms']=(time.perf_counter()-tick)*1000
   try:dungeon_type(40046)
   except ValueError as error:assert str(error)=='Unknown dungeons identity: 40046'
   else:raise AssertionError('Virtual graph ID accepted as native dungeon')
  try:dungeon_types()[34710]=7
  except TypeError:pass
  else:raise AssertionError('Static type map is mutable')
 finally:
  await c.asyncTearDown();out.update(own_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
 with tempfile.TemporaryDirectory(dir=h.H)as name:
  root=h.Path(name);cert=h.Path(h.os.environ['ELS_TEST_CERT_DIR']);app=Application(ServerConfig(mode='friends',port=0,state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',tls_cert=cert/'server-cert.pem',tls_key=cert/'server-key.pem'))
  try:
   with patch('els_server.domain.known_resurrection_maps.catalog',side_effect=ValueError('owned static mismatch')),patch('els_server.application.LocalAccount',wraps=LocalAccount)as account:
    try:await app.start()
    except ValueError as error:assert str(error)=='owned static mismatch'
    else:raise AssertionError('Invalid additional static catalog accepted')
    account.assert_not_called()
   assert not(root/'game.sqlite3').exists()and not(root/'accounts.sqlite3').exists()
  finally:app.close()
 assert not root.exists();out.update(ok=True,native_types=740,hp_map_entries=276,invalid_catalog_rejected_before_player_store=True,failure_runtime_removed=True)
 dest=h.H/'preparation-validation.json';assert not dest.exists();dest.write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
asyncio.run(main())
