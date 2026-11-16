"""Original 7FB/7FC/7FE/800/802/804/806/823 farm DTOs."""
import struct
from els_server.protocol.guild_system_messages import reply,text
from els_server.protocol.equipment_chip_messages import changes_wire

def plot(owner,slot,value): #DEC840, exact41-byte DTO.
    return struct.pack('>QiiQQ?Q',owner,slot,value['plant'],value['planted'],value['matures'],value['fertilized'],value['watered'])

def farms(rows): #2C25540 map<Q, Farm>, DDBB20 map<i32, Plot>.
    return struct.pack('>I',len(rows))+b''.join(struct.pack('>QQ',r['owner'],r['owner'])+text(r['name'])
        +struct.pack('>HiiQI',r['class_id'],0,r['water'],r['refill'],len(r['plots']))
        +b''.join(struct.pack('>i',slot)+plot(r['owner'],slot,value)for slot,value in sorted(r['plots'].items()))for r in rows)

def overview(rows,fertilizer,code=0):return reply(0x7fb,struct.pack('>ii',code,fertilizer)+farms(rows))
def updated(rows,kind=0x7fc):return reply(kind,bytes(4)+farms(rows))
def changed(kind,owner,slot,value,changes=(),code=0):
    return reply(kind,struct.pack('>i',code)+plot(owner,slot,value)+(changes_wire(changes)if kind in(0x7fe,0x804)else b''))
