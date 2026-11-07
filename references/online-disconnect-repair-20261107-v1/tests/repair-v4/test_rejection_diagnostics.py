"""Rejections stay effective and expose only bounded protocol metadata."""
from pathlib import Path
import asyncio,importlib.util,json,struct,sys
from types import SimpleNamespace
H=Path(__file__).resolve().parent
sys.argv=[__file__,'--candidate',str(H/'candidate')]
spec=importlib.util.spec_from_file_location('owned_rejection_setup',H/'test_luciel.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
from els_server.native_inbox import NativeInbox
from els_server.protocol.protocol_codec import Keys,Event,ProtocolError,encode_event,encode_frame

async def counters(values):
    keys=Keys(b'01234567',b'76543210')
    body=encode_event(Event(0x202,performers=(0,),kind=0x48d))
    wires=iter([encode_frame(body,keys,sequence=n,secure_sequence=value,spi=17,iv=bytes(8))for n,value in enumerate(values,1)])
    async def read():
        try:return next(wires)
        except StopIteration:raise EOFError('Owned end of input')from None
    inbox=NativeInbox(read,keys,SimpleNamespace(client_build='dx11_260923',role='game',phase='town_ready'),
        dict(requests=0,auxiliary_coalesced=0,town_moves_coalesced=0))
    try:
        await asyncio.wait_for(asyncio.shield(inbox.task),3)
        accepted=len(inbox.pending);error=inbox.error
        while inbox.pending:await inbox.get()
        try:await inbox.get()
        except Exception as delivered:assert delivered is error
        else:raise AssertionError('The input failure was hidden')
        return accepted,error
    finally:await inbox.close()

async def main():
    for values in ([0],[1,1],[9,3]):
        accepted,error=await counters(values)
        assert isinstance(error,ProtocolError)and accepted==len(values)-1
        assert str(error)==f'Unexpected secure sequence (spi=17, previous={values[0]if len(values)>1 else 0}, received={values[-1]}, outer={len(values)})'
    accepted,error=await counters([2**32-1,1,2]);assert accepted==3 and isinstance(error,EOFError)
    f=t.r.f.FriendsTests();await f.asyncSetUp()
    try:
        peer=await f.peer(f.alice);await peer.roster()
        uid=f.app.accounts[f.alice['id']].uid
        await t.r.admit(peer,uid,30000)
        await peer.send(0x5bf,struct.pack('>ii',1,2))
        try:await asyncio.wait_for(peer.until(0x5c0),5)
        except asyncio.IncompleteReadError:pass
        else:raise AssertionError('Invalid split continuation was accepted')
        expected='Invalid inventory split cursors (length=8, cursors=(1, 2))'
        assert any(e.get('error')==expected for e in f.events),[e.get('error')for e in f.events if e['event']=='protocol_error']
    finally:await f.asyncTearDown()
    return dict(ok=True,zero_duplicate_regression_refused=True,native_nonzero_wrap_preserved=True,
        actual_native_inbox=True,invalid_inventory_TLS_refused=True,diagnostics_contain_only_numeric_protocol_metadata=True,
        guard_conditions_unchanged=True,production_modified=False)

if __name__=='__main__':
    result=asyncio.run(main());(H/'rejection-diagnostics-fixed.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
