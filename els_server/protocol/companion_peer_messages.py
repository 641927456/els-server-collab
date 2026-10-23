"""Current owner-addressed companion notices; reuse the native pet DTO."""
import struct
from els_server.protocol.companion_messages import event,pet_record

def owner_uid(value):
    if type(value) is not int or not 0<value<2**63:raise ValueError('Peer companion owner UID')
    return value

def pet(owner,record=None):
    owner_uid(owner)
    if record is not None and (record.get('owner')!=owner or record.get('kind')!='pet' or not 0<record.get('uid',0)<2**63):
        raise ValueError('Peer owned pet record')
    return event(0x2ee,struct.pack('>QI',owner,int(record is not None))+(pet_record(record) if record is not None else b''))

def mount(owner,uid,unit):
    owner_uid(owner)
    if type(uid) is not int or not 0<uid<2**63 or type(unit) is not int or not 0<unit<10000:
        raise ValueError('Ordinary peer mount identity')
    # Current D790D0 has one extra byte over2014. Keep the ordinary false
    # constructor value; special10000..10003 transform mounts are excluded.
    return event(0x42e,struct.pack('>QQH?',owner,uid,unit,False))

def dismount(owner,unit):
    owner_uid(owner)
    if type(unit) is not int or not 0<unit<10000:raise ValueError('Ordinary peer mount type')
    return event(0x431,struct.pack('>QH?',owner,unit,False))
