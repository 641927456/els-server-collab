"""Unavailable coupon issuer: original failure ACK only, no redemption.

Original dialog limits text to20 UTF16 code units;1252870 rejects only empty
text before sending1A0 and registering1A1 wait. The940 response is a truthful
failure for bounded complete text, not an adjudication of legal issued codes.
No code validity/expiry, issuance, reward, cash order or withdrawal is adjudicated.
"""
import struct
from els_server.protocol.protocol_codec import Event


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x1a0:return None
    if (s.client_build!='dx11_260923' or not s.shop_test or s.role!='game'
        or s.phase!='town_ready' or type(sequence) is not int or not 1<=sequence<2**32
        or event.performers!=(0,) or event.uid!=2**64-1
        or event.target_uid!=2**64-1 or event.payload_mode!=0):return []
    payload=event.payload
    if len(payload)<10:return []
    size,=struct.unpack_from('>I',payload)
    if not 2<=size<=40 or size%2 or len(payload)!=size+8 or payload[-4:]!=bytes(4):return []
    try:text=payload[4:4+size].decode('utf-16le',errors='strict')
    except UnicodeDecodeError:return []
    if '\0' in text:return []
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if not current_lease(s):return []
    try:
        # Reuse the current stable selected-role/village-actor contract without
        # invoking preset Apply or any storage/economic action.
        from els_server.domain.avatar_set_flow import context
        context(s)
    except ValueError:return []
    return [Event(0x201,kind=0x1a1,payload=struct.pack('>i',940))]
