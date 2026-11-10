"""Current native guild readers; source RVAs retained at each body."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.guild_membership_profile import _string as text

def reply(kind,payload=b''):
    return Event(0x201,kind=kind,payload=payload)

def result(kind,value=0):return reply(kind,struct.pack('>i',value))

def menu(count,code=0): #324A860 and 27E updates: remaining daily guild-board posts.
    return reply(0x27c,struct.pack('>iB',code,count))

def expedition_summary(stage,joined,cleared,reward,code=0): #323C710 ->2407E60.
    return reply(0xace,struct.pack('>ib???',code,stage,joined,cleared,reward))

def join_rules(value,code=0):return reply(0x850,struct.pack('>i',code)+text(value))

def notice(category,uid,name='',message='',value=0,value2=0,extra=0):
    #3242F30: message type, target UID/name/text, two i32, Q, map<i32,i32>.
    return reply(0x284,struct.pack('>bQ',category,uid)+text(name)+text(message)+struct.pack('>iiQI',value,value2,extra,0))

def grade_ack(name,grade,code=0):return reply(0x28d,struct.pack('>i',code)+text(name)+bytes((grade,)))
def leave_ack(target,kicked,code=0):return reply(0x291,struct.pack('>i?Q',code,kicked,target))
def greeting_ack(deleted,code=0):return reply(0x293,struct.pack('>i?',code,deleted))

def member_row(row):
    #DA24E0 packed DTO: account,character,nickname,class,title,level,grade,
    # channel,map,position,login/logout,greeting,legacy PvP,rank strings,
    # lifetime/weekly GP,dates,counters,current combat rating and achievement.
    return (struct.pack('>QQ',row['account'],row['uid'])+text(row['name'])
        +struct.pack('>HiBBiibQQ',row['class_id'],0,row['level'],row['grade'],row['channel'],row['map'],row['position'],row['login'],row['logout'])
        +text(row['greeting'])+struct.pack('>QiQ',0,0,0)+text('')+bytes(2)
        +text('')+struct.pack('>ii',row['honor'],row['weekly_honor'])+text('')+text('')
        +struct.pack('>iiQiQi',0,0,0,0,row['combat'],0))

def member_greeting(row): #2C1F3B0.
    return (struct.pack('>Q',row['uid'])+text(row['name'])+struct.pack('>BHB',row['grade'],row['class_id'],row['level'])
        +text(row['greeting'])+struct.pack('>i',row['honor']))

def roster(page,pages,view,online,rows,code=0): #3247B60.
    position=rows if view!=2 else ()
    messages=rows if view==2 else ()
    return reply(0x27a,struct.pack('>iIIbiI',code,pages,page,view,online,len(position))
        +b''.join(member_row(r)for r in position)+struct.pack('>I',len(messages))+b''.join(member_greeting(r)for r in messages))

def posts(page,pages,category,rows,code=0): #324A320 -> DD9F40.
    return reply(0x280,struct.pack('>iIIBiI',code,pages,page,category,0,len(rows))+b''.join(
        struct.pack('>QQBBB',r['id'],r['owner'],1,r['category'],r['grade'])+text(r['name'])+text(r['text'])+text(r['date'])for r in rows))
