"""Bind original cumulative reports to the current run; project display only.

The report never authorizes a death, clear, reward, attribute or saved balance.
Each member supplies its own UID slice; observers' copies are never summed.
"""
from dataclasses import replace
import struct

from els_server.protocol.protocol_codec import Event
from els_server.protocol.pvp_play_messages import hp_report,report_ack


def generation(session):
    run=session.dungeon_run
    return (session.reward_run_id,run.stage if run is not None else session.gate_stage,
            run.part if run is not None else 0)


def report(session,event,sequence):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    if (event.event_id!=0x202 or event.kind!=0x9e or event.payload_mode!=0
        or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or event.performers not in ((),(0,)) or type(sequence)is not int or sequence<=0
        or session.phase!='dungeon_active' or not session.dungeon_substage_synced
        or not session.reward_run_id or not current_lease(session)):
        return [report_ack(2005)]
    try:
        parsed=hp_report(event.payload,statistics=True)
        if parsed.maximum_hp is not None:raise ValueError('PvP report in dungeon')
        local_cd=parsed.statistics['local_cooldown']
        if local_cd is not None and (0 in local_cd or session.account.uid in local_cd):
            raise ValueError('Dungeon cooldown excludes self and anonymous sources')
    except ValueError:
        return [report_ack(2005)]
    key=generation(session)
    previous=getattr(session,'dungeon_result_report',None)
    if previous is not None and previous[0]==key and sequence<=previous[1]:
        return [report_ack(0 if parsed.raw==previous[2].raw else 2005)]
    if session.clear_notified:
        # A native BB/471 retry rebuilds the DTO (HP and other fields may
        # change). Confirm its delivery without replacing the sealed result.
        return [report_ack(0 if previous is not None and previous[0]==key else 2005)]
    app=getattr(session,'application',None)
    room=app.world.dungeons.room(session) if app is not None else None
    members=room.members if room is not None else (session,)
    try:cooldown_payloads(members,session.dungeon_participants,replacement=(session,parsed.statistics))
    except ValueError:return [report_ack(2005)]
    session.dungeon_result_report=(key,sequence,parsed)
    return [report_ack(0)]


def current_statistics(session):
    saved=getattr(session,'dungeon_result_report',None)
    return saved[2].statistics if saved is not None and saved[0]==generation(session) else None




def cooldown_payloads(members,participants,*,replacement=None):
    totals={uid:0.0 for uid in participants}
    for recipient in members:
        stats=replacement[1] if replacement is not None and recipient is replacement[0] else current_statistics(recipient)
        if stats is not None and stats['local_cooldown'] is not None:
            for source,value in stats['local_cooldown'].items():
                if source in totals:totals[source]+=value
    try:return {uid:struct.pack('>f',value)for uid,value in totals.items()}
    except OverflowError as error:raise ValueError('Dungeon cooldown aggregate exceeds native f32')from error


def _reward_rates(effect):
    # DB8E60: category 1 = ED, 2 = EXP/ERP. 1005F30: 10 = mission, 11 = award.
    rates={}
    mission=effect.get('random_mission_percent')
    if mission:rates[2]={10:mission/100}
    award=effect.get('dungeon_result')
    if award:
        rate=award['bonus_bp']/10000
        if award['applied_ed']:rates[1]={11:rate}
        if award['ordinary_experience'] or award['resonance_experience']:
            rates.setdefault(2,{})[11]=rate
    data=bytearray(struct.pack('>I',len(rates)))
    for category,sources in sorted(rates.items()):
        data.extend(struct.pack('>BI',category,len(sources)))
        for source,rate in sources.items():
            data.extend(struct.pack('>Bf',source,rate))
    return data


def member_payload(payload,session,provided_cooldown=bytes(4),*,solo=False):
    # DA64C0 fixed header31, DA5DA0 constructor's empty-container member397.
    if len(payload)!=516 or struct.unpack_from('>I',payload,27)[0]!=1:
        raise ValueError('Dungeon result source member layout')
    row=bytearray(payload[31:428]);uid=session.account.uid
    if struct.unpack_from('>Q',row)[0]!=uid:raise ValueError('Dungeon result source owner')
    row[359-31:363-31]=provided_cooldown
    receipt=getattr(session,'reward_receipt',None)
    successful=payload[0x10]==1
    current_receipt=successful and receipt is not None and receipt.get('run_id')==session.reward_run_id
    if current_receipt:
        local_rules=receipt.get('local_rules')
        if local_rules is not None:
            # DA5DA0 wire92 -> member+49h -> GageItemArtifact. Kill EXP
            # belongs to cumulative growth, outside the clear award display.
            struct.pack_into('>Q',row,92-31,local_rules['artifact_experience']['clear'])
    # Original result revamp: successful single-player runs always award MVP.
    # This flag is independent of the unknown party score/rank formula.
    if solo and successful:row[388-31]=1
    stats=current_statistics(session)
    if stats is not None:
        damage=[values.get(uid,0.0) for values in stats['damage']]
        # Wire offsets from DA5DA0's field trace; 37ABAF0/37AD010 name the graphs.
        fields={273:damage[0],327:damage[1],331:damage[2],
                363:damage[3],367:damage[4],371:damage[5],
                335:damage[6],339:damage[7]}
        hp,mp,own_hp,own_mp=stats['recovery']
        fields.update({343:hp,347:mp,351:own_hp,355:own_mp})
        for offset,value in fields.items():struct.pack_into('>f',row,offset-31,value)
        struct.pack_into('>i',row,269-31,stats['received'])
    if current_receipt:
        # Insert the variable-length map after writing every fixed source offset.
        row[308-31:312-31]=_reward_rates(receipt.get('title_economy',{}))
    return bytes(row)


def seal(session,event=None):
    """Called within the existing dungeon worker domain after all adoption."""
    if not session.enter_dungeon or not session.clear_notified or not session.reward_run_id:return
    app=getattr(session,'application',None)
    room=app.world.dungeons.room(session) if app is not None else None
    members=room.members if room is not None else (session,)
    # Freeze before releasing the settlement domain, including when the C1
    # was queued to a mailbox. Socket timing and later selection are irrelevant.
    owner=room if room is not None else session
    epoch=room.seed if room is not None else session.reward_run_id
    saved=getattr(owner,'dungeon_result_rows',None)
    if saved is None or saved[0]!=epoch:
        if frozenset(m.account.uid for m in members)!=session.dungeon_participants:
            raise ValueError('Dungeon result admitted roster changed')
        rows=[]
        # Only the PVE1 map is scoped to one recipient. The original map may
        # contain remote observers' copies and must never be summed here.
        provided=cooldown_payloads(members,session.dungeon_participants)
        for member in members:
            if member is session and event is not None:source=event.payload
            elif getattr(member,'reward_receipt',None) is not None:
                source=member.reward_receipt['response']
            elif getattr(member,'dungeon_failed',False):
                from els_server.domain.dungeon_clear import failed_clear_notice
                source=failed_clear_notice(member.account.uid).payload
            else:raise ValueError('Dungeon result committed receipt missing')
            rows.append(member_payload(source,member,provided[member.account.uid],solo=len(members)==1))
        saved=(epoch,tuple(rows));owner.dungeon_result_rows=saved
    return saved


def project(session,event):
    if event.event_id!=0x201 or event.kind!=0xc1:return event
    saved=seal(session,event)
    if saved is None:return event
    payload=event.payload
    if len(payload)!=516:raise ValueError('Dungeon result source envelope')
    raw=payload[:27]+struct.pack('>I',len(saved[1]))+b''.join(saved[1])+payload[428:]
    return replace(event,payload=raw)


def finalize(session,messages):
    # _worker_call holds the original party/account domain here. Shared
    # writers have adopted all receipts, even when only BC is returned now.
    room=session.application.world.dungeons.room(session)
    if room is not None and all(m.clear_notified for m in room.members):seal(session)
    return [project(session,e)for e in messages]
