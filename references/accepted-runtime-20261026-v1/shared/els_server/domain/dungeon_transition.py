"""Isolated second-substage loader fixture, verified in the native B2 reader."""
from els_server.paths import PROJECT_ROOT
import json
from pathlib import Path
from els_server.protocol.protocol_codec import Event
def candidate_substage_one():
    data=json.loads((PROJECT_ROOT/'analysis/client-6c6b5180/next-substage-candidate.json').read_text(encoding='utf8'))
    if (data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
            or (data['event_id'],data['kind'],data['substage'],data['part'],data['size'])!=(0x201,0xb2,1,0,971)
            or data.get('retail_population') is not False):raise ValueError('Unsupported next-substage fixture')
    payload=bytes.fromhex(data['wire_hex'])
    if len(payload)!=971 or payload[:8]!=b'\0\0\0\1'+bytes(4):raise ValueError('Next-substage identity/length')
    return Event(0x201,kind=0xb2,payload=payload)
