"""A4B/A4C fields from native2B36590/2B36360; no premium grants."""
import struct
from els_server.protocol.protocol_codec import Event

def period(value):
    return Event(0x201,kind=0xa4c,payload=struct.pack('>iQQi',value['season'],value['begin'],value['end'],value['category']))

def status(value):
    # Native 2B3BE49 compares total XP at +10 to the stage threshold.
    # Offsets +14/+1c are reset timestamps; +24 is attendance.
    # Tail Qs are season start/end and server clock (native2B36590).
    rows=value['claimed'];tracks={track:sorted(step for t,step in rows if t==track)for track in sorted({t for t,s in rows})}
    data=struct.pack('>iiiiiQQQ',value['season'],value['tier'],value['daily_exp'],value['weekly_exp'],value['experience'],value.get('day',946656000),value.get('week',946656000),value['attendance']or 946656000)
    data+=struct.pack('>I',len(tracks))
    for track,steps in tracks.items():data+=struct.pack('>iI',track,len(steps))+b''.join(struct.pack('>i',step)for step in steps)
    data+=struct.pack('>iQQQ',value['category'],value['begin'],value['end'],value['now'])
    return Event(0x201,kind=0xa4b,payload=data)

def attendance_request(payload):
    if len(payload)!=5:raise ValueError('Pass attendance request length')
    category,display=struct.unpack('>iB',payload)
    if category not in(2,3,4)or display not in(0,1):raise ValueError('Pass attendance request category/flag')
    return category,bool(display)

def attendance_ack(category,display,*,result=0):
    return Event(0x201,kind=0xa4e,payload=struct.pack('>ii?',result,category,display))

def weekly_list(rows,*,result=0,limit=4):
    # C4F900 ->2BEA390: result,account limit,map<quest,pair<index,state>>.
    data=struct.pack('>iiI',result,limit,len(rows))
    data+=b''.join(struct.pack('>iii',qid,index,state)for qid,index,state in sorted(rows))
    return Event(0x201,kind=0xa64,payload=data)

def weekly_accept_ack(result=0):
    return Event(0x201,kind=0x6fc,payload=struct.pack('>i',result))

def reward_request(payload):
    offset=0
    def read():
        nonlocal offset
        if offset+4>len(payload):raise ValueError('Truncated pass reward request')
        v=struct.unpack_from('>i',payload,offset)[0];offset+=4;return v
    count=read();claims=[];tracks=set()
    if not 1<=count<=2:raise ValueError('Pass reward track count')
    for _ in range(count):
        track=read();n=read()
        if track not in(1,2)or track in tracks or not 1<=n<=50:raise ValueError('Pass reward step set')
        tracks.add(track)
        for _ in range(n):claims.append((track,read()))
    category=read();custom=read()
    if category not in(2,3,4)or custom or offset!=len(payload)or len(set(claims))!=len(claims):
        raise ValueError('Pass reward request identity or unsupported custom choice')
    return category,tuple(sorted(claims))

def reward_ack(plan=(),*,result=0):
    items={}
    for row in plan:items[row['template']]=items.get(row['template'],0)+row['quantity']
    data=struct.pack('>iI',result,len(items))+b''.join(struct.pack('>ii',t,n)for t,n in sorted(items.items()))+bytes(4)
    # Acquisition uses the existing verified D9 delta, in the same transaction.
    return Event(0x201,kind=0xa50,payload=data)

