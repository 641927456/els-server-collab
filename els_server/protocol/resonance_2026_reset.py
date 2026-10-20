"""Native612 current owned-inventory vector for reward-coin point refunds."""
from dataclasses import replace
import struct
from els_server.domain.fashion_state import move_ack

def inventory_reply(event,changes):
    if event.kind!=0x612 or event.payload[:4]!=bytes(4) or event.payload[-14:-10]!=bytes(4):
        raise ValueError('Complete successful no-item base reply required')
    if type(changes) is not tuple or len({p for p,_ in changes})!=len(changes):raise ValueError('Unique absolute inventory positions required')
    vector=move_ack(changes)[:-4]
    payload=event.payload[:-14]+vector+event.payload[-10:]
    if len(payload)>1024*1024-256:raise ValueError('Reset response exceeds transport frame budget')
    return replace(event,payload=payload)
