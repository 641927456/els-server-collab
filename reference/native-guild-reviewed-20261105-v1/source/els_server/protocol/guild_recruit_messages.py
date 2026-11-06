"""Current native guild recruitment DTOs (2BE..2CD)."""
import struct
from els_server.protocol.guild_system_messages import reply,text


def advertisement(row):
    # 2C1FA30; last fields are the saved guild value, type and capacity.
    return (struct.pack('>i',row['id'])+text(row['name'])+struct.pack('>Bi',row['level'],row['experience'])
        +text(row['master'])+struct.pack('>H',row['members'])+text(row['message'])
        +text(row['founded'])+text(row['registered'])+text(row['end'])
        +struct.pack('>iiH',row['extra'],row['type'],row['capacity']))


def advertisements(sort,pages,page,rows,can_manage,own):
    # 24212D0 has no result field before sort.
    return reply(0x2bf,struct.pack('>bIII',sort,pages,page,len(rows))
        +b''.join(map(advertisement,rows))+struct.pack('>??',can_manage,own))


def registered(kind,days,message,coins,result=0):
    return reply(kind+1,struct.pack('>ih',result,days)+text(message)+struct.pack('>i',coins))


def application(row):
    # 2C20060: class is u16; an additional i32 precedes level in this build.
    return (struct.pack('>iQ',row['guild'],row['owner'])+text(row['name'])
        +struct.pack('>HiB',row['class_id'],0,row['level'])+text(row['message'])
        +text(row['date'])+struct.pack('>Q',row['created']))


def applications(name,pages,page,rows,ads,result=0):
    return reply(0x2c9,struct.pack('>i',result)+text(name)+struct.pack('>III',pages,page,len(rows))
        +b''.join(map(application,rows))+struct.pack('>I',len(ads))+b''.join(map(advertisement,ads)))


def accepted(name,result=0):
    return reply(0x2cb,struct.pack('>i',result)+text(name))
