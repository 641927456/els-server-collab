"""Saved guild emblem collection and original five-part appearance."""
from functools import lru_cache
from els_server.domain import guild_rules as rules
from els_server.protocol.social_messages import Reader
from els_server.protocol import guild_emblem_messages as wire
from els_server.protocol.guild_system_messages import reply
from els_server.storage import guild_system_state as system
import struct,secrets

KINDS=frozenset((0x7db,0x7dd,0x7e3,0x7e5))
READS=frozenset((0x7db,))


@lru_cache(maxsize=1)
def definitions():return {r[0]['EMBLEM_ID']:r[0]for r in rules.calls('AddGuildEmblem')}


def parts(state):
    return state.get('emblem_details',{str(e):dict(level=0,remaining=0,expires=0)
        for e in state['emblems']})


def rows(state,now,*,equipped_only=False):
    result=[]
    for key,item in sorted(parts(state).items(),key=lambda r:int(r[0])):
        identity=int(key);category=definitions()[identity]['EMBLEM_TYPE']
        equipped=state['equipped_emblems'].get(str(category))==identity
        if equipped_only and not equipped:continue
        seconds=max(0,item['expires']-now)if item['expires']else item['remaining']
        result.append((category if equipped_only else identity,identity,category,equipped,(seconds+59)//60,item['level'],0))
    return tuple(result)


def shop_parts():
    return {r['ITEM_ID']:r for r in definitions().values()if r['ACQUISITION_CONDITION']==2}


def acquire(state,emblem,now):
    owned=parts(state)
    if str(emblem)in owned:raise ValueError('Guild emblem already owned')
    definition=definitions()[emblem]
    remaining=rules.calls('SetGuildEmblemRepairData')[0][0]*60 if 'PROTECTION_BUFF_TEMPLET_ID'in definition else 0
    owned[str(emblem)]=dict(level=0,remaining=remaining,expires=0)
    state['emblem_details']=owned
    return emblem


def guardian_ack(kind,state,identity,coins,now,*,result=0,success=False):
    item=parts(state).get(str(identity),dict(level=0,remaining=0,expires=0))
    seconds=max(0,item['expires']-now)if item['expires']else item['remaining']
    body=struct.pack('>iiiii',result,identity,item['level'],(seconds+59)//60,coins)
    return reply(kind+1,body+(bytes((success,))if kind==0x7e3 else b''))


def guardian(db,saved,kind,r,operation,now,randbelow):
    state=saved['system'];identity=r.scalar('i');owned=parts(state)
    definition=definitions().get(identity);item=owned.get(str(identity))
    if item is None or definition is None or 'PROTECTION_BUFF_TEMPLET_ID'not in definition:
        raise ValueError('Owned effect-bearing guild guardian required')
    if state['equipped_emblems']['4']==identity:raise ValueError('Unequip guild guardian before enhancement or repair')
    if kind==0x7e3:
        echoed=r.scalar('i');r.end()
        if echoed!=item['level']or not 0<=echoed<10:raise ValueError('Stale or maximal guild guardian level')
        data=rules.calls('AddGuildEmblemEnchantData')[0][0]['ENCHANT_DATA'][str(echoed+1)]
        cost=data['1'];probability=data['2']
        # The current ENCHANT_DATA defines a success probability and coin cost.
        # The original result DTO reports success plus the resulting saved level.
        if system.currency(db,saved['id'])[0]<cost:raise ValueError('Guild guardian enhancement coins')
        draw=randbelow(100)
        if type(draw)is not int or not 0<=draw<100:raise ValueError('Guild guardian random draw')
        success=draw<probability
        item['level']+=int(success)
    else:
        r.end();maximum,numerator,denominator=rules.calls('SetGuildEmblemRepairData')[0]
        minutes=(item['remaining']+59)//60
        spent=maximum-minutes
        if spent<10:raise ValueError('Guild guardian time already restored')
        # 2427100: ceil((max minutes-floor remaining minutes)*1/10).
        cost=(spent*numerator+denominator-1)//denominator
        item['remaining']=maximum*60;item['expires']=0;success=False
    coins,_=system.change_currency(db,saved['id'],-cost,0,operation,'guild-guardian-'+hex(kind),now)
    state['emblem_details']=owned;system.write(db,saved['id'],state)
    name=db.execute('SELECT name FROM characters WHERE uid=?',(saved['owner'],)).fetchone()[0]
    return [guardian_ack(kind,state,identity,coins,now,success=success)],[wire.changed(rows(state,now),name)]


def command(db,s,event,saved,operation,now,randbelow=None):
    r=Reader(event.payload);state=saved['system']
    if event.kind==0x7db:
        r.end();return [wire.owned(rows(state,now))],[]
    if not rules.permission(saved,state,3):raise ValueError('Guild emblem funds authority')
    if event.kind in(0x7e3,0x7e5):return guardian(db,saved,event.kind,r,operation,now,secrets.randbelow if randbelow is None else randbelow)
    if r.scalar('I')!=5:raise ValueError('Complete five-part guild emblem required')
    owned=parts(state);selected={}
    for _ in range(5):
        category=r.scalar('i');identity=r.scalar('i');part_type=r.scalar('i');equipped=r.scalar('B')
        remaining=r.scalar('i');level=r.scalar('i');extra=r.scalar('i')
        if category not in range(5)or str(category)in selected or str(identity)not in owned:raise ValueError('Guild emblem category/owned part')
        if part_type!=category or definitions()[identity]['EMBLEM_TYPE']!=category or equipped not in(0,1):raise ValueError('Guild emblem source differs from owned part')
        # Echoed level, time and extra are display state; saved values remain authoritative.
        selected[str(category)]=identity
    r.end()
    if selected==state['equipped_emblems']:raise ValueError('Guild emblem appearance unchanged')
    old=state['equipped_emblems'].get('4');new=selected['4']
    if old!=new:
        previous=owned[str(old)]
        if previous['expires']:previous['remaining']=max(0,previous['expires']-now);previous['expires']=0
        current=owned[str(new)]
        if current['remaining']:current['expires']=now+current['remaining']
    coins,_=system.change_currency(db,saved['id'],-10,0,operation,'guild-emblem-appearance',now)
    state['emblem_details']=owned;state['equipped_emblems']=selected;system.write(db,saved['id'],state)
    name=db.execute('SELECT name FROM characters WHERE uid=?',(saved['owner'],)).fetchone()[0]
    return [reply(0x7de,struct.pack('>ii',0,coins))],[wire.changed(rows(state,now),name)]


def failure(kind):
    if kind in(0x7e3,0x7e5):return guardian_ack(kind,{'emblems':[]},0,0,0,result=1)
    return wire.owned((),1)if kind==0x7db else reply(kind+1,struct.pack('>ii',1,0))


def replay(db,saved,kind,payload,now,old):
    identity=struct.unpack_from('>i',payload)[0]
    if str(identity)not in parts(saved['system']):raise ValueError('Guild guardian receipt lost ownership')
    success=bool(bytes.fromhex(old['events'][0][1])[-1])if kind==0x7e3 else False
    return [guardian_ack(kind,saved['system'],identity,system.currency(db,saved['id'])[0],now,success=success)]
