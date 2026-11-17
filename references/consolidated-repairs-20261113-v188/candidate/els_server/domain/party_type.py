"""Native A45/A46/A47 waiting-party type conversion."""
import struct
from els_server.protocol.protocol_codec import Event


def change(world,session,event):
    def ack(result):return [Event(0x201,kind=0xa46,payload=struct.pack('>i',result))]
    party=world.party_of.get(session)
    if (event.event_id!=0x202 or event.payload_mode!=0 or len(event.payload)!=1
        or event.payload[0] not in (1,3) or party is None
        or party['leader'] is not session or party['run'] is not None
        or party.get('recruitment',{}).get('published')
        or any(party.get(k)for k in ('solo_challenge','challenge','challenge_pending','union_party','racing','pet_fight'))):
        return ack(2)
    members=tuple(party['members']);kind=event.payload[0];maximum=4 if kind==1 else 6
    if (not 1<=len(members)<=maximum or any(m.released or m.phase!='town_ready'
        or m not in world.members or world.party_of.get(m)is not party
        or world.dungeons.room(m)is not None for m in members)):
        return ack(2)
    # Native2D7B540 consumes only the type and room capacity. Selection is
    # independent; the next145 selects a dungeon appropriate to the new type.
    notice=Event(0x201,kind=0xa47,payload=bytes((kind,maximum)))
    response=ack(0)
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.local_session import SessionOrderError
    try:boxes=_prepared_boxes([(m,[notice])for m in members],response)
    except SessionOrderError:return ack(2)
    changed=bool(party.get('raid_party'))!=(kind==3)
    if changed:
        party['raid_party']=kind==3;party['ready'].clear();party.pop('admission',None)
        party.pop('recruitment',None)
        world.invitations={m:v for m,v in world.invitations.items()if v.get('party')is not party}
    for m,box in boxes.items():m.mailbox=box
    if changed:
        from els_server.domain.party_entry_consent import cancel
        cancel(world.dungeons,party)
    return response
