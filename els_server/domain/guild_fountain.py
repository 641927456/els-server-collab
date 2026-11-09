"""Current ACF/AD0/AD1 fountain: five native sockets, per-stage pity and weekly reset."""
import secrets,struct
from els_server.domain import guild_rules as rules
from els_server.storage import guild_system_state as system
from els_server.protocol.social_messages import Reader
from els_server.protocol.guild_system_messages import reply,result

KINDS=frozenset((0xacf,))

def rows(state,now):
    if state['fountain_week']!=rules.week(now):return tuple((0,0)for _ in range(5))
    return tuple(tuple(state['fountain'].get(str(n),(0,0)))for n in range(5))

def vector(values):
    if len(values)!=5:raise ValueError('Current fountain has five stages')
    return struct.pack('>I',5)+b''.join(struct.pack('>iB',socket,count)for socket,count in values)

def notice(owner,values):return reply(0xad1,struct.pack('>Q',owner)+vector(values))

def command(db,s,event,saved,operation,now):
    state=saved['system'];r=Reader(event.payload);stage=r.scalar('i');count=r.scalar('I')
    if count!=5:raise ValueError('Fountain current vector required')
    previous=tuple((r.scalar('i'),r.scalar('B'))for _ in range(count));choice=r.scalar('i');r.end()
    actual=rows(state,now)
    if stage not in range(5)or previous!=actual or not rules.permission(saved,state,3):raise ValueError('Guild fountain authority/stage/stale state')
    pool=[tuple(v)for v in rules.calls('SetGuildFountainSocket')if v[0]==stage]
    if sum(v[2]for v in pool)!=100:raise ValueError('Current fountain source weights')
    if choice:
        if actual[stage][1]<rules.calls('SetGuildFountainCeilingCount')[0][0]or not any(v[1]==choice and v[3]for v in pool):raise ValueError('Fountain selected maximum requires full pity of this stage')
        value=choice;pity=0
    else:
        cost=dict(rules.calls('SetGuildFountainCost'))[stage]
        system.change_currency(db,saved['id'],-cost,0,operation,'current fountain stage'+str(stage),now)
        roll=secrets.randbelow(100)
        for row in pool:
            roll-=row[2]
            if roll<0:value=row[1];break
        pity=min(rules.calls('SetGuildFountainCeilingCount')[0][0],actual[stage][1]+1)
    current=list(actual);current[stage]=(value,pity)
    state['fountain']={str(n):list(v)for n,v in enumerate(current)};state['fountain_week']=rules.week(now)
    system.write(db,saved['id'],state)
    return [result(0xad0)],[notice(saved['owner'],current),reply(0x7ec,struct.pack('>i',system.currency(db,saved['id'])[0]))]

def failure(kind):return result(0xad0,1)
