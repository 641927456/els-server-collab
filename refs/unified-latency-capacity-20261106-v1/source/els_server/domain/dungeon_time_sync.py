"""The existing DX11 clock eligibility, shared by worker and transport."""
from els_server.protocol.protocol_codec import Event

def context(session):
    if (session.client_build!='dx11_260923' or not session.enter_dungeon
        or session.role!='game' or session.phase!='dungeon_active'
        or not session.dungeon_substage_synced):return None
    run=session.dungeon_run
    return (session.shop_session_id,session.account.uid,session.reward_run_id,session.gate_stage,
        id(run),getattr(run,'stage',None),getattr(run,'part',None))

def notification():return Event(0x201,kind=0x9c,payload=bytes(4))
