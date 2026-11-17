"""Native CP from the signed support producer; bind it to the current owned inputs.

As with the existing Guild native-CP protocol, the client computes this value.
This is not an independent server-side anti-cheat computation.
"""
import hashlib,json,math,struct,sqlite3,time
from contextlib import closing
from els_server.domain.raid_admission import native_definition

MAGIC=0x52435031
PARTY_DISPLAY_MAGIC=0x50435031
PARTY_DISPLAY_REPORT_TTL=10


def active_pet(account):
    from els_server.storage.companion_state import rows
    with closing(sqlite3.connect(account.store.path,timeout=10))as db:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():return None
        row=db.execute('SELECT pet FROM companion_active WHERE owner=?',(account.uid,)).fetchone()
        if not row or not row[0]:return None
        pet=next((p for p in rows(db,account.uid,'pet')if p['uid']==row[0]),None)
        if pet is None:raise ValueError('Raid CP active owned pet missing')
        return dict(pet,current=not pet.get('expires_at')or time.time()<pet['expires_at'])


def _inputs(session, *, equipped_only=False):
    account=session.account
    character=account.character()
    items=account.get_inventory_snapshot(equipped_only=equipped_only)['items']
    from els_server.domain.character_stats import equipment_contributes
    effective=[(i['uid'],equipment_contributes(i,character))for i in items if i['group']==9]
    return character,items,account.get_skills(),effective,active_pet(account)


def _basis(session,inputs):
    source=json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()
    return session.account,session.account.uid,session.shop_session_id,hashlib.sha256(source).digest()


def basis(session,*,equipped_only=False):
    return _basis(session,_inputs(session,equipped_only=equipped_only))


def _retry_basis(session,inputs):
    # A clear changes fatigue, result history and stored EXP even when every
    # active combat input is unchanged. Keep levels, allocations, titles,
    # skill pages, collection, pet and every equipped instance in the proof.
    character,items,skills,effective,pet=inputs
    relevant={k:v for k,v in character.items() if k not in (
        'normal_fatigue','cleared_dungeons','known_resurrection_count')}
    if character.get('resonance') is not None:
        relevant['resonance']={k:v for k,v in character['resonance'].items() if k not in ('experience','revision')}
    if character.get('artifact') is not None:
        relevant['artifact']={k:v for k,v in character['artifact'].items() if k!='experience'}
    from els_server.storage.inventory_state import EQUIPPED_GROUPS
    from els_server.domain.item_expiration import expired
    equipped=[(item,expired(item)) for item in items if item['group'] in EQUIPPED_GROUPS]
    return _basis(session,(relevant,equipped,skills,effective,pet))


def request(session,payload,*,fresh=False):
    if fresh:session._raid_native_power=None
    if len(payload)<16 or payload[-16:-12]!=struct.pack('>I',MAGIC):return payload
    magic,owner,value=struct.unpack('>IQf',payload[-16:])
    if owner!=session.account.uid or not math.isfinite(value) or not 0<=value<=4294967040:
        raise ValueError('Raid native CP source/number')
    from els_server.domain.equipment_chip_flow import current_lease
    if not current_lease(session):raise ValueError('Raid native CP current actor')
    inputs=_inputs(session)
    session._raid_native_power=(_basis(session,inputs),value,_retry_basis(session,inputs))
    return payload[:-16]


def allowed(session,identity,*,retry=False):
    native=native_definition(identity)
    if native is None:return True
    required=native.get('limitCombatCapability',0)
    if not required:return True
    proof=getattr(session,'_raid_native_power',None)
    if proof is None or proof[1]*100<required*95:return False
    inputs=_inputs(session)
    return (proof[0]==_basis(session,inputs)
            or retry and len(proof)==3 and proof[2]==_retry_basis(session,inputs))


def party_display_request(session,event):
    """Remove a footer only at the exact end of the native request body."""
    from dataclasses import replace
    payload=event.payload
    if len(payload)<16 or payload[-16:-12]!=struct.pack('>I',PARTY_DISPLAY_MAGIC):
        return event,None
    body_size=len(payload)-16
    if event.kind==0x136:
        if body_size<46:return event,None
        name_size=struct.unpack_from('>I',payload,8)[0]
        title_at=27+name_size
        if title_at+4>body_size:return event,None
        expected=46+name_size+struct.unpack_from('>I',payload,title_at)[0]
    elif event.kind==0x8ee:
        if body_size<30:return event,None
        expected=30+struct.unpack_from('>I',payload,11)[0]
    else:
        expected=30 if event.kind==0x139 else 8
    if body_size!=expected:return event,None
    _,owner,value=struct.unpack('>IQf',payload[-16:])
    if owner!=session.account.uid or not math.isfinite(value) or not 0<=value<=4294967040:
        value=None
    return replace(event,payload=payload[:body_size]),value


def remember_party_display(session,value):
    if value is None:return
    from els_server.domain.equipment_chip_flow import current_lease
    if session.phase=='town_ready' and current_lease(session):
        session._party_display_power=(basis(session,equipped_only=True),value)
        session._party_periodic_display=None


def _party_periodic_owner(session):
    return session.account,session.account.uid,session.shop_session_id,session.npc_history_id


def party_display_power(session):
    periodic=getattr(session,'_party_periodic_display',None)
    if (periodic is not None and session.phase=='town_ready' and periodic[3]>time.monotonic()
        and periodic[0]==_party_periodic_owner(session)):
        from els_server.domain.equipment_chip_flow import current_lease
        if current_lease(session):return periodic[1]
    proof=getattr(session,'_party_display_power',None)
    if proof is not None and proof[0]==basis(session,equipped_only=True):
        return proof[1]
    return 0.0


def party_display_report(session,event):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.domain.session_auxiliary import friends_auxiliary_session
    if (not friends_auxiliary_session(session) or session.phase!='town_ready'
        or event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1
        or event.payload_mode or len(event.payload)!=12):return
    world=session.application.world
    party=world.party_of.get(session)
    if (not party or any(m not in world.members or m.phase!='town_ready' for m in party['members'])
        or any(party.get(k) for k in ('run','union_runs','pet_fight','racing','solo_challenge'))):return
    uid,value=struct.unpack('>Qf',event.payload)
    if uid!=session.account.uid or not math.isfinite(value) or not 0<=value<=4294967040:return
    now=time.monotonic()
    if now<getattr(session,'_party_display_next',0) or not current_lease(session):return
    session._party_display_next=now+2
    level=session.account.character().get('resonance',{}).get('level',0)
    proof=(_party_periodic_owner(session),value,level)
    previous=getattr(session,'_party_periodic_display',None)
    session._party_periodic_display=(*proof,now+PARTY_DISPLAY_REPORT_TTL)
    if previous is not None and previous[:3]==proof and previous[3]>now:return
    if party.get('union_party'):
        from els_server.protocol.union_messages import snapshot
        notice=snapshot(party)
        for member in party['members']:world.send(member,notice)
    else:
        from els_server.protocol.social_messages import party_member_update
        notice=party_member_update(session)
        for member in party['members']:world.send(member,notice)
