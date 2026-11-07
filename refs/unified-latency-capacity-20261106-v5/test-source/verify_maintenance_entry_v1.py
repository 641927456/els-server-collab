import runtime_fixture as h
import asyncio,json,struct,sys,secrets
from unittest.mock import patch
from els_server.transport import GameServer
from els_server.storage.characters import Characters

async def main():
    c=h.f.FriendsTests();owner=secrets.token_hex(24)
    def server(config,app,log):
        gate=config.accounts_file.with_name('maintenance-admission.json')
        gate.write_text(json.dumps(dict(owner=owner,allowed_account_ids=[c.alice['id']])),'utf8')
        return GameServer(config,app,log)
    with patch.object(h.f,'GameServer',server):await c.asyncSetUp()
    gate=c.server.admission_path
    async def rejected(account,role=None):
        bridge=c.bridge(account)
        try:await bridge.remote(role=role)
        except ValueError as error:assert str(error)=='Account authentication failed'
        else:raise AssertionError('Maintenance admitted an unauthorized or disabled account')
    try:
        assert c.app.registry.authenticate(c.bob['name'],c.bob['token'])['id']==c.bob['id']
        await rejected(c.bob);await rejected(c.bob,role='relay')
        bad=dict(c.alice,token='0'*64);await rejected(bad)
        peer=await c.peer(c.alice);await peer.roster()
        uid=Characters(c.config.state_file,c.alice['id']).list()[0]['uid']
        await peer.enter_town(uid)
        # While admission is restricted, existing game requests never read it.
        path_type=type(gate);original_stat=path_type.stat
        def denied_stat(path,*args,**kwargs):
            if path==gate:raise PermissionError('owned admission I/O failure')
            return original_stat(path,*args,**kwargs)
        with patch.object(path_type,'stat',denied_stat):
            await peer.send(0x48d);await peer.until(0x48f)
            try:c.server._check_maintenance_admission(dict(id=c.alice['id']))
            except PermissionError:pass
            else:raise AssertionError('A permission failure silently opened admission')
        await peer.close();c.peers.remove(peer)
        async with asyncio.timeout(5):
            while c.alice['id']in c.app.playing:await asyncio.sleep(.01)
        # A valid allowlisted ID still has to pass the original live registry.
        c.app.registry.disable(c.alice['name']);await rejected(c.alice)
        assert c.app.registry.enabled(c.bob['id'])and not c.app.registry.enabled(c.alice['id'])
        # Malformed startup policy must not bind a game listener.
        gate.write_text(json.dumps(dict(owner=owner,allowed_account_ids=[True])),'utf8')
        malformed=GameServer(c.config,c.app,lambda *args,**kwargs:None)
        try:
            try:await malformed.start()
            except ValueError as error:assert str(error)=='Invalid maintenance admission policy'
            else:raise AssertionError('Malformed maintenance policy silently started')
            assert malformed.listener is None and malformed.realtime is None
        finally:await malformed.close()
        gate.unlink()
        # Opening maintenance takes effect on the same actual server process.
        bob=await c.peer(c.bob);await bob.roster();await bob.close();c.peers.remove(bob)
        assert c.server._maintenance_accounts is None
        with patch.object(path_type,'stat',denied_stat):
            again=await c.peer(c.bob);await again.roster();await again.close();c.peers.remove(again)
        await rejected(c.alice)
        assert not sys._is_gil_enabled()
        out=dict(passed=True,actual_native_TLS_and_credential_authentication=True,allowed_account_reaches_native_town=True,ordinary_valid_account_and_relay_rejected=True,invalid_token_and_disabled_allowlisted_account_rejected=True,original_live_registry_authority_retained=True,existing_native_game_requests_have_no_maintenance_IO=True,permission_error_does_not_open_admission=True,malformed_startup_policy_no_listener=True,policy_removal_opens_same_server_without_restart=True,opened_server_has_no_further_policy_file_reads=True,shared_code_no_local_auth_branch=True,GIL_enabled=False)
    finally:await c.asyncTearDown()
    out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections))
    (h.H/'maintenance-entry-native-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
from els_server.__main__ import _native_timing
with _native_timing():asyncio.run(main())
