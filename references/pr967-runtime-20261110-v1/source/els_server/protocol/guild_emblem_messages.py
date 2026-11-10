"""Native map<int, GuildEmblemInfo>: emblem ID, category, active, time, level."""
import struct
from els_server.protocol.guild_system_messages import reply,text


def collection(rows):
    return struct.pack('>I',len(rows))+b''.join(struct.pack('>iii?iii',key,identity,category,equipped,remaining,level,extra)
        for key,identity,category,equipped,remaining,level,extra in rows)


def owned(rows,result=0):return reply(0x7dc,struct.pack('>i',result)+collection(rows))


def changed(rows,author):return reply(0x7df,bytes(4)+collection(rows)+text(author))
