"""Native 60/61 tutorial admission and initial loading; no completion/reward grant.



1392740 supplies these exact character-specific tutorial maps. 13E54B0

writes a RoomInfo; 13E0C80 reads result, RoomInfo, member slots and a string.

The client's original tutorial resource scripts retain their own NPC groups.

"""

import math,struct,hashlib

from els_server.protocol.protocol_codec import Event

from els_server.protocol.local_messages import i32,u32,wstring

from els_server.protocol.dungeon_messages import member,initial_part,begin_substage

MAPS={1:41150,2:41160,3:41170,4:41190,5:41180,6:41290,7:41210,8:41220,9:41230,10:41240,11:41250,12:41420,13:41570,14:34570,15:35240}



def request(payload,unit_type):

    """Read bounded D9B710/D9BCC0 fields, retaining the native room byte layout."""

    if not isinstance(payload,bytes) or len(payload)>2048:raise ValueError('Tutorial room bound')

    pos=0;fields={};locations={}

    def scalar(fmt):

        nonlocal pos

        n=struct.calcsize('>'+fmt)

        if pos+n>len(payload):raise ValueError('Tutorial room truncated')

        v=struct.unpack_from('>'+fmt,payload,pos)[0];pos+=n;return v

    def string():

        nonlocal pos

        n=scalar('I')

        if n>256 or n%2 or pos+n>len(payload):raise ValueError('Tutorial string')

        v=payload[pos:pos+n].decode('utf-16le');pos+=n;return v

    schema=((0,'B'),(1,'Q'),(9,'I'),(0xd,'s'),(0x2d,'B'),(0x2e,'B'),(0x2f,'B'),(0x30,'s'),(0x50,'B'),(0x51,'B'),(0x52,'s'),(0x72,'H'),(0x74,'s'),(0x94,'B'),(0x95,'B'),(0x96,'B'),(0x97,'i'),(0x9b,'B'),(0x9c,'B'),(0x9d,'f'),(0xa1,'H'),(0xa3,'H'),(0xa5,'Q'),(0xad,'i'),(0xb1,'B'),(0xb2,'i'),(0xb6,'B'),(0xb7,'B'),(0xb8,'Q'),(0xc0,'Q'),(0xc8,'i'),(0xcc,'B'))

    for off,fmt in schema:locations[off]=pos;fields[off]=string() if fmt=='s' else scalar(fmt)

    def mapping(key_fmt):

        count=scalar('I')

        if count>16:raise ValueError('Tutorial option count')

        result={}

        for _ in range(count):

            k=scalar(key_fmt);v=scalar('i')

            if k in result:raise ValueError('Tutorial duplicate option')

            result[k]=v

        return result

    fields[0xcd]=mapping('H')

    for off,fmt in ((0xdd,'B'),(0xde,'B'),(0xdf,'i'),(0xe3,'B'),(0xe4,'B'),(0xe5,'Q')):fields[off]=scalar(fmt)

    fields[0xed]=mapping('i')

    for off,fmt in ((0xfd,'B'),(0xfe,'i'),(0x102,'Q'),(0x10a,'Q')):fields[off]=scalar(fmt)

    if pos!=len(payload) or fields[0xd]!='tutorial' or fields[0xb2]!=MAPS.get(unit_type):raise ValueError('Tutorial source/map mismatch')

    if fields[1]!=0 or fields[9]!=0 or fields[0]!=1 or fields[0x50]!=1 or not math.isfinite(fields[0x9d]):raise ValueError('Tutorial room identity')

    from els_server.game_data import client_data

    definition=client_data().dungeon(fields[0xb2])

    if 'Tutorial' not in definition['dataFileName'] and unit_type<14:raise ValueError('Tutorial definition')

    return fields[0xb2],payload[:locations[1]]+struct.pack('>Q',10001)+payload[locations[1]+8:]



def admission(room,account):

    # D9DDB0 slot type4 is the existing verified single-player master/actor.

    slot=b'\0\4\1'+bytes(3)+i32(0)+u32(1)+member(account.get_skills(),account.character(),account.get_inventory_snapshot()['items'],account_id=account.account_id)+u32(0)+bytes(4)

    return Event(0x201,kind=0x61,payload=i32(0)+room+u32(1)+slot+wstring(''))



def start_notice(ack):

    # 14A/2F867A0: ushort, identical RoomInfo/member slots, empty opposing

    # slots, string and metadata vectors. Tutorial rooms start automatically.

    return Event(0x201,kind=0x14a,payload=bytes(2)+ack.payload[4:-4]+u32(0)+wstring('')+u32(0)*3)



def initialization(session=None):

    if session is not None:return session.first_story_entry['run'].population_event()

    # Empty replacement maps preserve the ORIGINAL resource tutorial groups;

    # supplying an explicit empty part would instead erase their NPC groups.

    return Event(0x201,kind=0xb2,payload=i32(0)*2+u32(0)*2+struct.pack('>f',0)+b'\0'+u32(0)*3+i32(0)*2+u32(0)*3)



def handle(s,event):

    if s.client_build!='dx11_260923' or not s.enter_town or not s.enter_dungeon or s.role!='game' or event.event_id!=0x202:return None

    owned=(event.performers==(0,) and event.uid==event.target_uid==2**64-1 and event.payload_mode==0)

    current=getattr(s,'first_story_entry',None)

    if event.kind==0x60:

        if current is not None and s.dungeon_run is current['run'] and owned and event.payload==current['request'] and s.phase in ('dungeon_loading','dungeon_active'):return [current['admission']]

        if not owned or s.phase!='map_loading' or 0x32 not in s.completed or s.account.characters is None:return []

        character=s.account.character()

        if character.get('pending_delete') or character['level']!=1 or s.account.get_reward_balances()['experience']!=0:return []

        try:identity,room=request(event.payload,character['unit_type'])

        except (ValueError,UnicodeError,struct.error):return []

        reply=admission(room,s.account)

        from els_server.domain.first_story_population import TutorialRun

        run=TutorialRun(identity)

        s.first_story_entry=dict(map=identity,request=event.payload,admission=reply,started=False,run=run)

        s.dungeon_id=identity;s.phase='dungeon_loading';s.dungeon_run=run;s.dungeon_requested=False;s.dungeon_substage_synced=False

        return [reply,start_notice(reply)]

    if current is None:return None
    # An ordinary room replaces dungeon_run; a returned tutorial must not
    # consume that room's loading, death or clear messages.
    if s.dungeon_run is not current['run']:return None

    if event.kind==0x91 and owned and s.phase in ('dungeon_loading','dungeon_active'):

        if len(event.payload)!=8:return []

        progress,mode=struct.unpack('>ii',event.payload)

        if not 0<=progress<=100 or mode!=0:return []

        reply=[Event(0x201,kind=0x92,payload=i32(0)+i32(progress)+u32(0)),Event(0x201,kind=0x93,payload=struct.pack('>Q',s.account.uid)+i32(progress))]

        if progress==100 and s.phase=='dungeon_loading':s.phase='dungeon_active';reply += [Event(0x201,kind=0x96,payload=b''),initialization(s)]

        return reply

    if event.kind==0xb3 and owned and s.phase=='dungeon_active':

        if len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []

        value=struct.unpack_from('>f',event.payload,5)[0]

        if not math.isfinite(value) or not 0<=value<=1e9:return []

        reply=[Event(0x201,kind=0xb4,payload=i32(0)),Event(0x201,kind=0xb5,payload=i32(0)+struct.pack('>Q',s.account.uid))]

        if not s.dungeon_substage_synced:

            reply += [Event(0x201,kind=0xb6,payload=bytes(16)),initial_part(current['run'].part),begin_substage(current['run'].part)]


            current['started']=True;s.dungeon_substage_synced=True

            s.dungeon_clock.resume();current['run'].loaded()

        return reply

    run=current['run']

    if event.kind==0xad:

        if not owned or s.phase!='dungeon_active' or not s.dungeon_substage_synced:return []

        from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice

        try:d=death_report(event.payload)

        except ValueError:return []

        npc=next((n for n in run.current['npcs'] if n['key']==d['index']),None)
        if d['index']==0:
            from els_server.domain.first_story_retirements import original_controller
            resolved=original_controller(s,run,d)
            if resolved is not None:npc=resolved

        if npc is None:return []
        index=npc['key']

        hp=struct.unpack('>f',struct.pack('>I',d['hp_bits']))[0]

        # Original Lithia dummy5 retires through 16E1760 with positive HP;
        # its source deliberately omits NO_DROP. It is not a combat kill.
        source_retirement=(npc['no_drop'] or (run.identity==35240 and run.stage==0 and run.part==2 and npc['template']==9288))
        script_retirement=(source_retirement and d['flag']==255 and d['status']==1

            and d['source']==d['killer']==2**64-1 and d['last_uid'] in (0,2**64-4)

            and d['extra_uid']==0 and not d['contribution'] and not d['counters']

            and (d['readiness']=={s.account.uid:0}
                 or d['readiness']=={s.account.uid:1} and s.account.character()['unit_type']==10))

        ids={s.account.uid,0,2**64-1} if not npc['active'] and npc['no_drop'] else {s.account.uid}

        if not script_retirement and (d['flag'] not in (0,1) or any(d[k] not in ids for k in ('source','killer','last_uid'))

            or any(uid!=s.account.uid for k in ('contribution','readiness','counters') for uid in d[k])):return []

        if not math.isfinite(hp) or hp<=0:return []

        previous=run.defeated.get(index)

        if previous is not None:return [death_ack()] if previous==event.payload else []

        if s.clear_notified:return []

        run.defeated[index]=bytes(event.payload);s.defeated_npcs=run.defeated

        # Source controllers retire without a loot grant. The original source

        # conditions still decide each part; there is no timer/fixture clear.

        from els_server.domain.dungeon_flow import periodic

        return [death_ack(),empty_reward_death_notice(index,d['killer'])]+periodic(s)

    if event.kind==0x110:

        # C38760 -> 110 is the original result-exit handshake. Tutorial maps

        # suppress the ordinary result window; the source-clear room is over.

        # Game v278/1044730 -> 1AB3BF0 accepts a successful 68 independently

        # of a pending 67 and runs its original v578 town continuation.

        if not owned or event.payload or not s.clear_notified:return []

        reply=[Event(0x201,kind=0x111,payload=bytes(12))]

        if current.get('returned'):return reply

        if s.phase!='dungeon_active':return []

        from els_server.protocol.dungeon_messages import end_ack

        sync=s.saved_user_sync(clear_reward_only=True)

        current['returned']=True;s.phase='map_loading';s.pending_map=None

        s.dungeon_return_pending=True;s.inventory_town_sync_sent=True

        return reply+[end_ack(),sync]

    if event.kind==0xbb and owned and s.phase=='dungeon_active':

        if event.payload!=struct.pack('>b',run.part):

            from els_server.domain.dungeon_flow import handle as late_transition

            return late_transition(s,event)

        if not s.part_end_notified:return []

        if not run.poll_ready():return []

        if run.next['kind']==4:

            # This tutorial only introduces combat. Starter rewards retain

            # their actual resource quest IDs/quantities and manual claim.

            from els_server.domain.dungeon_clear import reward_clear_notice

            def encode(balances,best):return reward_clear_notice(0,0,s.account.uid,elapsed_seconds=s.dungeon_clock.seconds(),best_seconds=best).payload

            proof=(b'first-story-source-clear-v1'+bytes.fromhex(run.graph['source_sha256'])

                +struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)

                +b''.join(struct.pack('>iI',k,len(v))+v for k,v in sorted(run.defeated.items())))

            if not s.clear_notified:

                receipt=s.account.reward_store.grant(run.run_id,proof,0,0,encode,dungeon_clear=(run.identity,s.dungeon_clock.seconds()))

                s.reward_receipt={'run_id':run.run_id,**receipt};s.clear_notified=True

            return [Event(0x201,kind=0xbc,payload=i32(0)),Event(0x201,kind=0xc1,payload=s.reward_receipt['response'])]

        # Existing native part/stage transitions, with this source-bound graph.

        from els_server.domain.dungeon_flow import handle as transition

        return transition(s,event)

    return None

