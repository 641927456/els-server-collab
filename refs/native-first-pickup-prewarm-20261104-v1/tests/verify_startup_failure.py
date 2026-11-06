"""Invalid static economy definitions fail before opening a player account."""
import runtime_fixture as h
import asyncio,json,tempfile
from unittest.mock import patch
from els_server.application import Application,LocalAccount
from els_server.config import ServerConfig
async def main():
 with tempfile.TemporaryDirectory(dir=h.H)as name:
  root=h.Path(name);cert=h.Path(h.os.environ['ELS_TEST_CERT_DIR'])
  app=Application(ServerConfig(mode='friends',port=0,state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',tls_cert=cert/'server-cert.pem',tls_key=cert/'server-key.pem'))
  try:
   with patch('els_server.domain.el_search_effects.catalog',side_effect=ValueError('owned static catalog mismatch'))as catalog,patch('els_server.application.LocalAccount',wraps=LocalAccount)as account:
    try:await app.start()
    except ValueError as error:assert str(error)=='owned static catalog mismatch'
    else:raise AssertionError('Invalid static catalog accepted')
    catalog.assert_called_once_with();account.assert_not_called()
   assert not(root/'game.sqlite3').exists()and not(root/'accounts.sqlite3').exists()
  finally:app.close()
 assert not root.exists()
 result=dict(ok=True,invalid_catalog_rejected_before_player_account=True,no_player_databases_created=True,own_runtime_removed=True)
 (h.H/'startup-failure-test.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
asyncio.run(main())
