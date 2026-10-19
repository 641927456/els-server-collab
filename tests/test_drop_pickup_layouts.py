"""Both observed original request layouts work; unknown permutations fail closed."""
import json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from drop_pickup import potion_pickup_request,PREFIX_DROP_ID_XOR
run=ROOT/'analysis/client-6c6b5180/20261014-005553'
events=json.loads((run/'pickup-layout-counterexample.json').read_text(encoding='utf8'))['requests']
requests=[bytes.fromhex(e['payload_hex']) for e in events if e.get('event')=='decoded_client_event' and e.get('kind')==0xd0]
assert [potion_pickup_request(p)['drop_id'] for p in requests]==[910001,910002,910003]
assert all(potion_pickup_request(p)['layout']=='nonce_first' for p in requests)
for changed in ('length','body','id','flag','xyz'):
    b=bytearray(requests[0]);n=struct.unpack_from('>I',b,0)[0];start=8+n
    if changed=='length':struct.pack_into('>I',b,0,n+1)
    elif changed=='body':b[start+8]=2
    elif changed=='id':struct.pack_into('>I',b,4+n,PREFIX_DROP_ID_XOR)
    elif changed=='flag':b[start+320]=0
    elif changed=='xyz':struct.pack_into('>f',b,start+321,float('nan'))
    try:potion_pickup_request(bytes(b))
    except ValueError:continue
    raise AssertionError('Malformed prefix layout accepted')
print('PASS: second original layout, three issued IDs and variable prefix lengths match; corrupt prefix/body/ID/flag/positions rejected.')
