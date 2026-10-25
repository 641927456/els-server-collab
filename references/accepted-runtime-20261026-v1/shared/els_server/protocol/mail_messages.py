"""Native PostBox wire fields recovered from the pinned DX11 reader/writer.

1CC/1CD list, 1D6/1D7 delete, 1D2/1D3 read, 1D4/1D5 claim.
Only ED attachments are enabled; inventory attachment data is server-owned.
"""
import datetime
import struct
from functools import lru_cache
from els_server.protocol.local_messages import wstring


def list_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=7:
        raise ValueError('Mail list request size')
    folder,page,sort,refresh=struct.unpack('>BiBB',payload)
    if folder>4 or not 1<=page<=100000 or sort>3 or refresh>1:
        raise ValueError('Invalid mail list request')
    return folder,page,sort,refresh


def read_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=8:raise ValueError('Mail read request size')
    value=struct.unpack('>Q',payload)[0]
    if not 1<=value<2**63:raise ValueError('Invalid mail ID')
    return value


def selection_request(payload,claim=False):
    if not isinstance(payload,bytes) or len(payload)<4:raise ValueError('Mail selection size')
    n=struct.unpack_from('>I',payload)[0]
    # 1D4 additionally carries a vector of client attachment hints and two bools.
    # ED-only inbox entries have no inventory hints. Nonempty hints are rejected.
    expected=4+n*8+(6 if claim else 0)
    if not 1<=n<=10 or len(payload)!=expected:raise ValueError('Mail selection bound')
    ids=list(struct.unpack_from('>'+'Q'*n,payload,4))
    if len(set(ids))!=n or any(not 1<=i<2**63 for i in ids):raise ValueError('Invalid mail selection')
    if claim and (payload[-6:-2]!=bytes(4) or payload[-2] not in (0,1) or payload[-1] not in (0,1)):
        raise ValueError('Unsupported attachment hints')
    return ids


def date(value):
    return datetime.datetime.fromtimestamp(value,datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


@lru_cache(maxsize=1)
def empty_item():
    from els_server.domain.inventory_items import fixture
    seed=fixture();raw=bytearray.fromhex(seed['wire_hex'])
    for f in seed['fields']:
        off=int(f['offset'],0);pos=f['wire_offset']
        if off==0:struct.pack_into('>I',raw,pos,0)
        elif off==4:raw[pos]=0
        elif off==5:struct.pack_into('>i',raw,pos,0)
    return bytes(raw)


def attachment(row):
    return row['ed'] if row.get('claimed_at') is None else 0


def header(row):
    # Header DTO +0 UID, +8 type, +9 attachment indicator, +D ED,
    # +15 item, +409 recipient, +429 sender, +449 title,
    # +469 new/unread flag, +46A auxiliary u16, +46C expiry string.
    ed=attachment(row)
    return (struct.pack('>QBiQ',row['id'],row.get('mail_type',0),int(ed>0),ed)+empty_item()
            +wstring(row.get('recipient',''))+wstring(row['sender'])+wstring(row['title'])
            +struct.pack('>BH',int(row.get('read_at') is None),0)+wstring(date(row['expires_at'])))


def list_ack(rows=(),total=0,page=1,folder=0,result=0):
    # 2DE0E60 -> 2C1C3C0: result,total,vector<header>,page,folder,bool,u8.
    return (struct.pack('>iiI',result,total,len(rows))+b''.join(header(r) for r in rows)
            +struct.pack('>iBBB',page,folder,0,0))


def detail(row):
    ed=attachment(row)
    return (struct.pack('>QQQBi',row['id'],0,row['created_at'],row.get('mail_type',0),int(ed>0))
            +wstring(row.get('recipient',''))+wstring(row['sender'])+wstring(row['title'])+wstring(row['body'])
            +struct.pack('>BH',int(row.get('read_at') is None),0)+wstring(date(row['created_at']))
            +struct.pack('>QQ',ed,0)+empty_item()+struct.pack('>Q',row['expires_at']))


def read_ack(row=None,result=0):
    if row is None:
        row=dict(id=0,created_at=1,expires_at=1,ed=0,claimed_at=1,sender='',title='',body='',read_at=None)
    # result,detail,map<byte,int> capacity notices,vector<auxiliary items>.
    return struct.pack('>i',result)+detail(row)+bytes(8)


def delete_ack(ids=(),result=0):
    # 2DE3460: result,vector<UID>,capacity notices,auxiliary items.
    return struct.pack('>iI',result,len(ids))+b''.join(struct.pack('>Q',i) for i in ids)+bytes(8)


def claim_ack(ids=(),ed=0,result=0):
    # 2C1CCB0: UID,u8,map<template,count>,vector<inventory row>,ABSOLUTE ED.
    # Sending absolute current ED makes duplicate network replies harmless.
    return (struct.pack('>iI',result,len(ids))
            +b''.join(struct.pack('>QBIIQ',i,0,0,0,ed) for i in ids)+bytes(8))
