"""Ordinary fixed cube presentation, using the original 197 result layout."""
import struct
from collections import Counter
from els_server.domain.fashion_state import move_ack
from els_server.protocol.protocol_codec import Event


def result(ed,changes=(),rewards=(),code=0):
    totals=Counter()
    for template,quantity in rewards:totals[template]+=quantity
    rewards=sorted(totals.items())
    vector=move_ack(changes)[:-4]
    wire=(struct.pack('>iiiI',(500) if code == -1 else code,0,0,len(rewards))+b''.join(struct.pack('>ii',*r) for r in rewards)
        +vector+struct.pack('>QBBBi',ed,0,0,0,0))
    acknowledgement=Event(0x201,kind=0x197,payload=wire)
    return [Event(0x201,kind=0xad8,payload=vector),acknowledgement] if changes else [acknowledgement]
