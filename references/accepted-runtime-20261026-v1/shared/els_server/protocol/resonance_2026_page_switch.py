"""Current client page-tab route: 0x79E signed i32 -> 0x79F.

0x614 is a different response and must not be used for the active page tab.
D3A990 consumes result followed by the full0x610 state and clears old points.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.resonance_2026_state import ResonanceCharacterState


def page_switch_request(payload):
    if type(payload) is not bytes or len(payload) != 4:
        raise ValueError('Page switch requires exactly one signed i32')
    page, = struct.unpack('>i', payload)
    if not 1 <= page <= 4:
        raise ValueError('Invalid resonance page')
    return page


def page_switch_reply(*, result, state):
    if type(result) is not int or not -2**31 <= result < 2**31:
        raise ValueError('Explicit original result code required')
    if type(state) is not ResonanceCharacterState:
        raise ValueError('Complete explicit resonance state required')
    return Event(0x201, kind=0x79F, payload=struct.pack('>i', result)+state.notice().payload)
