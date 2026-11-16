"""Actual TLS entry/AD reports; explicit fixture floats, not native measurements."""
import math,struct
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def footer(uid,first,second,side=0,*,entry=True):
    raw=struct.pack('>4sQffB3s',b'GRP2',uid,first,second,side,bytes(3))
    if not entry:return raw
    f32=lambda value:struct.unpack('>f',struct.pack('>f',value))[0]
    return struct.pack('>4sQf',b'RCP1',uid,f32(math.floor(f32(max(first,second)+.5))))+raw

def first_native_actor(payload):
    from els_server.domain.dungeon_npcs import MODE0_FIELDS
    stage,part,groups,group,empty,count=struct.unpack_from('>iiIiII',payload)
    assert (stage,part,groups,group,empty)==(0,0,1,0,0) and count==8
    cursor=24+count*sum(width for _,width,_,_ in MODE0_FIELDS)+29
    assert struct.unpack_from('>I',payload,cursor)[0]==count;cursor+=4
    key,template=struct.unpack_from('>ii',payload,cursor);cursor+=4+5
    assert key==0 and template>0
    for index in range(6):
        if index==4:assert payload[cursor]==1;cursor+=1
        size=struct.unpack_from('>I',payload,cursor)[0];cursor+=4+size
        assert cursor+98<=len(payload)
    bits=struct.unpack_from('>I',payload,cursor+4)[0]
    assert struct.unpack('>f',struct.pack('>I',bits))[0]>0
    return key,bits

async def check(row,peer,*,phase):
    uid=row['uid'];side=int(phase!='test')
    if phase=='test':
        for value,expected in ((3989.,2224),(3990.,0)):
            ack=await peer.request(0x7d4,struct.pack('>ii',1,34310)+footer(uid,value,value),0x7d5)
            assert struct.unpack_from('>i',ack.payload)[0]==expected
    # Entry is Lu; the second connection switches through the real 38E consumer
    # after B3, so the server's active side and later GRP2 report agree.
    values=(3999.5,4000.5)
    ack=await peer.request(0x7d4,struct.pack('>ii',1,30000)+footer(uid,*values),0x7d5)
    assert ack.payload[:4]==bytes(4)
    ack=await peer.request(0x382,ENTRY+footer(uid,*values),0x383);assert ack.payload[:4]==bytes(4)
    await peer.until(0x14a);await peer.request(0x91,struct.pack('>ii',100,0),0x92)
    population=await peer.until(0xb2);key,hp_bits=first_native_actor(population.payload)
    ack=await peer.request(0xb3,bytes(9),0xb4);assert ack.payload[:4]==bytes(4)
    await peer.until(0xbd)
    if side:
        status=bytearray(62);status[54]=1
        from els_server.protocol.luciel_status_messages import request
        assert request(bytes(status))==1
        await peer.request(0x38e,bytes(status))
    # The first declared native El Tree actor is key0. Serialize the published
    # AD layout from named fields and this connection's emitted maximum HP; this is the
    # existing protocol acceptance path, not an authoritative damage simulation.
    death=(struct.pack('>iBQQ6fBI',key,0,uid,uid,0.,0.,0.,0.,0.,0.,0,hp_bits)
           +struct.pack('>IIQIQ',0,0,0,0,uid))
    from els_server.domain.dungeon_lifecycle import death_report
    assert death_report(death)['killer']==uid
    payload=death+footer(uid,*values,side,entry=False)
    for _ in range(2):
        ack=await peer.request(0xad,payload,0xae);assert ack.payload==bytes(4)
    return dict(ok=True,actual_TLS=True,native_session=False,phase=phase,side=side,fixture_raw=values[side],entry_boundaries=phase=='test',AD_replayed=True,natural_battle=False)
