"""Public TLS roster and town responses, without repeat economic operations."""
import ipaddress,struct
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig

async def check(rows,*,runtime,progress,require_public=True,phase='test'):
    peers=[];cases=[]
    try:
        for row in rows:
            if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
            peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])));peers.append(peer)
            await enter(peer,row['uid'])
            roster=next(event for event in peer.events if event.kind==0x488)
            assert roster.payload[:4]==bytes(4)and struct.unpack_from('>I',roster.payload,24)[0]==len(row['role_uids'])
            assert any(event.kind==0x228 and event.payload[:4]==bytes(4)for event in peer.events)
            guide=[event for event in peer.events if event.kind==0x2b]
            assert guide,'Missing actual character/quest state reply'
            cases.append(dict(unit=row['unit'],roles=len(row['role_uids']),roster_bytes=len(roster.payload),guide_messages=len(guide),town_ready=True))
        progress('roster-town-complete',cases=cases)
        return dict(ok=True,phase=phase,public_network=require_public,actual_TLS=True,cases=cases,natural_GUI=False,natural_battle=False,economic_requests=0)
    finally:
        for peer in peers:await peer.close()
