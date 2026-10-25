"""Original common quest record shape projected from the selected boost task."""
import struct
from els_server.storage.character_schema import character_uid
from els_server.protocol.protocol_codec import Event


def active_record(definition,row,*,owner_uid):
    task=definition.task(row['id']);at=row['accepted_at'];count=row['count']
    if type(at) is not int or not 0<=at<2**64 or type(count) is not int or not 0<=count<=task.required_count<=65535:
        raise ValueError('Invalid authoritative campaign objective state')
    return (struct.pack('>iQQI',task.quest_id,character_uid(owner_uid),0,1)
            +struct.pack('>iHB',task.subquest_id,count,int(count>=task.required_count)))


def accepted(definition,row,*,owner_uid):
    return Event(0x201,kind=0xf0,payload=active_record(definition,row,owner_uid=owner_uid)+bytes(12))


def progress(definition,row,*,owner_uid):
    return Event(0x201,kind=0xf3,payload=struct.pack('>I',1)+active_record(definition,row,owner_uid=owner_uid))
