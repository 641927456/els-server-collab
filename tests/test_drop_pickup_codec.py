"""Validate both actual original D0 requests and reject tampered potion shapes."""
import json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drop_pickup import potion_pickup_request,DROP_ID_XOR
run=ROOT/'analysis/client-6c6b5180/20261014-002737'
events=json.loads((run/'world-drop-probe-snapshot.json').read_text(encoding='utf8'))['server']
requests=[bytes.fromhex(e['payload_hex']) for e in events if e.get('event')=='decoded_client_event' and e.get('kind')==0xd0]
assert [potion_pickup_request(p)['drop_id'] for p in requests]==[910001,910002]
def reject(edit):
    b=bytearray(requests[0]);edit(b)
    try:potion_pickup_request(bytes(b))
    except ValueError:return
    raise AssertionError('Malformed pickup shape accepted')
reject(lambda b:b.__setitem__(8,2))
reject(lambda b:struct.pack_into('>I',b,320,DROP_ID_XOR))
reject(lambda b:b.__setitem__(324,0))
reject(lambda b:struct.pack_into('>f',b,325,float('nan')))
reject(lambda b:struct.pack_into('>I',b,349,2049))
reject(lambda b:b.pop())
print('PASS: distinct original IDs and variable opaque suffixes decode; tampered body/ID/flag/position/length rejected.')
