"""Only a verified eligible death issues one experimental ground spawn."""
import json
import struct
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from dungeon_population import population
from dungeon_drops import potion_drop_notice
from dungeon_lifecycle import death_report
body=bytes.fromhex(json.loads((ROOT/'analysis/client-6c6b5180/20261013-160720/death-event-header.json').read_text(encoding='utf8'))[0]['payload'])
args={'enter_town':True,'enter_dungeon':True,'client_build':'dx11_260923','npc_slot_test':True,'gate_test':True,'population_test':True,'clear_test':True,'reward_test':True,'item_test':True,'drop_probe':True}
def report(n):
    b=bytearray(body)
    struct.pack_into('>i',b,0,n['key'])
    struct.pack_into('>f',b,46,n['hp'])
    return Event(0x202,performers=(0,),kind=0xad,payload=bytes(b))
with tempfile.TemporaryDirectory() as directory:
    account=LocalAccount(LocalState(Path(directory)/'save.sqlite3'))
    session=LocalSession(account,**args)
    session.role='game';session.phase='dungeon_active';session.dungeon_substage_synced=True;session.reward_run_id='test-run'
    before=account.get_inventory_snapshot()
    stage=population(0)
    first=report(stage['npcs'][0])
    assert [m.kind for m in session.handle(first)]==[0xae,0xaf,0xcf]
    assert session.world_drop_sequence==910002 and len(session.world_drops)==1
    assert session.world_drop_issued['payload_hex']==potion_drop_notice(910001,death_report(first.payload)['xyz'][3:]).payload.hex()
    assert [m.kind for m in session.handle(first)]==[0xae] and len(session.world_drops)==1
    bad=bytearray(report(stage['npcs'][1]).payload);struct.pack_into('>Q',bad,5,1002)
    assert session.handle(Event(0x202,performers=(0,),kind=0xad,payload=bytes(bad)))==[]
    for n in stage['npcs'][1:]:
        reply=session.handle(report(n))
        if not n['active'] or n['no_drop'] or n['key']==stage['clear_key']:
            assert all(m.kind!=0xcf for m in reply)
    assert account.get_inventory_snapshot()==before
    # Final Boss is a real eligible death, unlike the two exit gates. The
    # ground notice must precede PartEnd, without prematurely granting items.
    session.gate_stage=2;session.defeated_npcs={};session.part_end_notified=False
    boss=report(population(2)['npcs'][0]);count=len(session.world_drops)
    assert [m.kind for m in session.handle(boss)]==[0xae,0xaf,0xcf,0xba]
    assert session.world_drop_issued['stage']==2 and session.world_drop_issued['npc_key']==0
    assert len(session.world_drops)==count+1 and not session.world_drop_issued['pickup_committed']
    assert account.get_inventory_snapshot()==before
    assert [m.kind for m in session.handle(boss)]==[0xae] and len(session.world_drops)==count+1
try:LocalSession(drop_probe=True)
except ValueError:pass
else:raise AssertionError('Unisolated drop probe accepted')
print('PASS: eligible native identity emits one CF; duplicate/foreign/no-drop/gate reports do not issue grants or repeat drops.')
