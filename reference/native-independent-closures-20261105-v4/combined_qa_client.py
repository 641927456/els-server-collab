"""Ordinary authenticated native requests, usable on owned private or public QA."""
from pathlib import Path
import asyncio,hashlib,json,ssl,struct
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.friends_relay import read_packet,data_packet,read_data
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,encode_event,encode_frame,decode_frame,decode_event,read_welcome
from els_server.protocol import photo_zone_messages as wire

class Peer:
    async def send(self,kind,payload=b''):
        self.writer.write(encode_frame(encode_event(Event(0x202,kind=kind,payload=payload,performers=(0,))),
                          self.keys,spi=self.spi,sequence=self.outgoing))
        self.outgoing+=1;await self.writer.drain()
    async def until(self,kind):
        async with asyncio.timeout(25):
            for _ in range(400):
                head=await self.reader.readexactly(8)
                raw=head+await self.reader.readexactly(struct.unpack_from('<I',head)[0]-8)
                event=decode_event(decode_frame(raw,self.keys,expected_sequence=self.incoming).plaintext)
                self.incoming+=1;self.received.append(event)
                if event.kind==kind:return event
        raise AssertionError('Native reply missing '+hex(kind))
    async def query(self,kind,payload=b'',reply=None):
        await self.send(kind,payload);answer=await self.until(kind+1 if reply is None else reply)
        await self.send(0x48d);await self.until(0x48f)
        return answer
    async def close(self):
        self.writer.close()
        try:await self.writer.wait_closed()
        except ssl.SSLError as error:
            if error.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise
        await self.bridge.close()

async def connect(identity,peers):
    from els_server.domain.town_travel import catalog
    p=Peer();p.bridge=Bridge(BridgeConfig(**identity['bridge']))
    p.reader,p.writer=await p.bridge.remote();p.keys=BOOTSTRAP_KEYS;p.incoming=1;p.received=[];peers.append(p)
    p.spi,p.keys=read_welcome(await p.until(1));p.outgoing=1
    for kind,reply in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
        await p.send(kind);await p.until(reply)
    xyz=catalog()['towns']['20001']['xyz']
    for kind,reply,body in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',identity['uid'])),
        (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
        (0x225,0x226,struct.pack('>iB',20001,0)),(0x227,0x228,struct.pack('>fffBH',*xyz,0,0))):
        await p.send(kind,body);answer=await p.until(reply)
        if kind in(0x225,0x227):assert answer.payload[:4]==bytes(4)
    await p.send(0x48d);await p.until(0x48f)
    return p

def mail_request(recipient,item,count):
    from els_server.protocol.player_mail_messages import grammars,send_request
    values=dict(recipient=recipient,title='Owned attachment',body='Owned QA',ed=0,item=item,count=count,flag=0,extra=0)
    parts=[]
    for field in grammars()[0]['fields']:
        kind=field['kind']
        if kind=='noise':parts.append(struct.pack('>I',4)+b'ownq')
        elif kind=='wstring':parts.append(wire.wstring(values[field['field']]))
        else:parts.append((values[field['field']]^int(field['mask'],0)).to_bytes({'byte':1,'u32':4,'u64':8}[kind],'big'))
    payload=b''.join(parts);assert send_request(payload)==values
    return payload

def chat(text,channel=0,name='',uid=2**64-1):
    return(bytes((channel,0))+struct.pack('>Q',uid)+wire.wstring(name)+wire.wstring(text)+wire.wstring('')
        +struct.pack('>iQBiQiI',-1,2**64-1,0,0,0,0,0))


async def qualify_pet_gems(peer,snapshot,report):
    before=snapshot();egg=next(i for i in before[0]['items']if i['template']==500051)
    gems=[i for i in before[0]['items']if i['template']==135974];assert len(gems)==3
    async def action(kind,body,code=0):
        answer=await peer.query(kind,body,kind+1)
        assert struct.unpack_from('>i',answer.payload)[0]==code,(hex(kind),answer.payload[:16].hex())
        return answer
    await action(0x2e8,struct.pack('>Q',egg['uid'])+wire.wstring('OwnedGemPet'))
    created=snapshot();pet,=created[0]['pets'];uid=pet['uid']
    equipment=lambda item,slot:struct.pack('>QiQ',uid,slot,item['uid'])
    await action(0x8c7,equipment(gems[0],1),-1);assert snapshot()==created
    money=created[0]['money']['ed']
    await action(0x438,struct.pack('>QBIi',gems[0]['uid'],0,0,1))
    current=snapshot();assert current[0]['money']['ed']==money-150
    identified=[next(i for i in current[0]['items']if i['uid']==g['uid'])for g in gems]
    assert all(g['identified']and len(g['option_groups']['1'])==1 for g in identified)
    await action(0x438,struct.pack('>QBIi',gems[0]['uid'],0,0,0),1);assert snapshot()==current
    for slot,g in enumerate(identified[:2],1):
        await action(0x8c7,equipment(g,slot))
        after=snapshot();equipped=next(e for e in after[0]['pet_equipment']if e['pet']==uid and e['slot']==slot)
        assert equipped['socket']==g['option_groups']['1'][0]and equipped['item_uid']==g['uid']
        assert all(i['uid']!=g['uid']for i in after[0]['items'])
        assert after[0]['money']['ed']==current[0]['money']['ed']
    after=snapshot();assert after[1:]==before[1:]
    report['checks'].append('Native pet activation, pending equip rejection, mode1 identification of three owned gems for150 ED, re-identification rejection and two saved socket equips; equipment uses persisted options without a new draw')
    report['pet_gems']=dict(fee_per_gem=50,identified=3,equipped=2,cold_reconnect=False)
    return dict(pet=uid,equipment=after[0]['pet_equipment'],tradable=identified[2])


async def qualify_personal_trade(peers,uids,snapshot,report,gem):
    async def action(index,kind,body=b'',code=0):
        answer=await peers[index].query(kind,body,kind+1)
        assert struct.unpack_from('>i',answer.payload)[0]==code,(hex(kind),answer.payload[:16].hex())
        return answer
    await action(0,0x174,struct.pack('>Q',uids[1]));await peers[1].until(0x176)
    await peers[1].query(0x177,struct.pack('>QBi',uids[0],1,0),0x179)
    await peers[0].query(0x48d,b'',0x48f)
    before=snapshot();assert any(i==gem for i in before[0]['items'])
    await action(0,0x17f,struct.pack('>QiB',gem['uid'],1,0))
    await action(0,0x182,struct.pack('>Q',101));await action(1,0x182,struct.pack('>Q',20))
    await action(0,0x185);await action(1,0x185)
    await action(0,0x188);assert snapshot()==before
    await action(1,0x188);await peers[0].query(0x48d,b'',0x48f)
    after=snapshot();assert after[0]['money']['ed']==before[0]['money']['ed']-82
    assert after[1]['money']['ed']==before[1]['money']['ed']+76 and after[2]==before[2]
    assert all(i['uid']!=gem['uid']for i in after[0]['items'])
    received=next(i for i in after[1]['items']if i['uid']==gem['uid'])
    assert {k:v for k,v in received.items()if k!='slot'}=={k:v for k,v in gem.items()if k!='slot'}
    await action(1,0x188,code=-1);assert snapshot()==after
    await action(0,0x174,struct.pack('>Q',uids[1]));await peers[1].until(0x176)
    await action(0,0x17a,struct.pack('>i',0x72));await peers[1].query(0x48d,b'',0x48f)
    assert snapshot()==after
    report['checks'].append('Native personal trade registers and confirms both actors before atomic settlement; identified pet gem UID/options preserved, ED101/20 exchanges charge6 total fee, duplicate final approval and cancellation cannot grant again')
    report['personal_trade']=dict(item_uid=gem['uid'],receiver=uids[1],fee=6,cold_reconnect=False)
    return dict(owner=uids[1],item=received)


def verify_pet_and_trade_cold(snapshot,pet,trade,report):
    rows=snapshot();assert rows[0]['pet_equipment']==pet['equipment']
    assert next(i for i in rows[1]['items']if i['uid']==trade['item']['uid'])==trade['item']
    report['pet_gems']['cold_reconnect']=True;report['personal_trade']['cold_reconnect']=True
    report['checks'].append('Both authenticated cold reconnects retain the two pet sockets and the exact identified gem at its new owner')


async def scenario(identities,snapshot,report,leave):
    peers=[];relays=[]
    async def action(index,kind,body=b'',reply=None,success=True):
        answer=await peers[index].query(kind,body,reply)
        assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:16].hex())
        return answer
    async def poll(index):await peers[index].query(0x48d,reply=0x48f)
    try:
        assert len(identities)==3
        for identity in identities:await connect(identity,peers)
        initial=snapshot();uids=[i['uid']for i in identities]
        report['checks'].append('Three owned authenticated characters enter the normal town')
        assert not any(i['template']==288494 for i in initial[0]['items'])
        catalog=await peers[0].query(0x80d,struct.pack('>i',1),0x80e)
        assert catalog.payload[0]==1
        count=struct.unpack_from('>I',catalog.payload,1)[0]
        assert len(catalog.payload)==5+28*count
        offers=[struct.unpack_from('>Iiiiiii',catalog.payload,5+28*i)for i in range(count)]
        assert [p for p in offers if p[0]==1200288494]==[(1200288494,288494,41,50,0,1,0)]
        purchased=await action(0,0x80f,struct.pack('>IIH',1,1200288494,2),0x810)
        before=snapshot()
        tickets=[i for i in before[0]['items']if i['template']==288494]
        assert len(tickets)==1 and tickets[0]['count']==2
        assert before[0]['money']['ed']==initial[0]['money']['ed']-100
        assert struct.unpack_from('>Q',purchased.payload,len(purchased.payload)-8)[0]==before[0]['money']['ed']
        assert before[0]['money']['experience']==initial[0]['money']['experience']
        report['checks'].append('Native80D/80E lists the approved50 ED ticket; actual80F/810 buys two for100 ED and delivers the owned stack without EXP change')
        for index in (0,1):
            await action(index,0x248,wire.wstring(identities[2]['character_name'])+wire.wstring('Owned presence'))
            await action(2,0x24b,struct.pack('>Q',uids[index]));await poll(index)
        ticket=next(i for i in before[0]['items']if i['template']==288494)
        await action(0,0x5b8,struct.pack('>QH',ticket['uid'],1052))
        await action(0,0x5b8,struct.pack('>QH',ticket['uid'],1052),success=False)
        await action(1,0x5a2,wire.room(world=1052,name='ForeignLocked'),success=False)
        await action(0,0xe44,struct.pack('>Q',773)+wire.wstring('OwnedStudio')+struct.pack('>i',21))
        marks=[len(p.received)for p in peers]
        created=await action(0,0x5a2,wire.room(world=1052,name='OwnedStudio',public=False,password='owned'))
        room_id=struct.unpack_from('>Q',created.payload,5)[0]
        assert created.payload[-1:]==b'\1'
        await action(1,0x5a4,struct.pack('>Q',room_id)+wire.wstring('wrong'),success=False)
        joined=await action(1,0x5a4,struct.pack('>Q',room_id)+wire.wstring('owned'))
        assert joined.payload[-1:]==b'\0'
        listed=await action(2,0x5ac,struct.pack('>iH',1,65535))
        assert wire.wstring('owned')not in listed.payload
        await poll(2)
        entered=[e for e in peers[2].received[marks[2]:]if e.kind==0x262]
        assert all(any(e.payload[4:12]==struct.pack('>Q',uid)and e.payload[-5:-1]==struct.pack('>i',1052)for e in entered)for uid in uids[:2])
        current=snapshot();assert sum(i['count']for i in current[0]['items']if i['template']==288494)==ticket['count']-1
        assert 1052 in current[0]['unlocked']and 1052 not in current[1]['unlocked']
        report['checks'].append('One ticket unlocks one owner background; duplicate and foreign unlocks fail; private room, name check, camera ownership and friend maps are current')
        async def packet(reader,kind):
            async with asyncio.timeout(10):
                while True:
                    value=await read_packet(reader)
                    if value[0]==kind:return value
        for index in(0,1):relays.append(await peers[index].bridge.remote(role='relay'))
        manifests=[json.loads((await packet(reader,1))[1:])for reader,_ in relays]
        assert all({p['uid']for p in m['peers']}==set(uids[:2])for m in manifests)
        payload=data_packet(manifests[0]['epoch'],uids[1],b'owned-closure-relay')
        relays[0][1].write(struct.pack('>I',len(payload))+payload);await relays[0][1].drain()
        assert read_data(await packet(relays[1][0],2))==(manifests[0]['epoch'],uids[0],b'owned-closure-relay')
        for _,writer in relays:writer.close();await writer.wait_closed()
        relays.clear()
        report['checks'].append('Actual authenticated relay forwards opaque room traffic with server-owned sender UID')
        marks=[len(p.received)for p in peers]
        await action(0,0x85,chat('Owned studio message'))
        for index in(1,2):await poll(index)
        assert all(any(e.kind==0x87 and wire.wstring('Owned studio message')in e.payload for e in peers[i].received[marks[i]:])for i in(0,1))
        assert not any(e.kind==0x87 for e in peers[2].received[marks[2]:])
        await action(2,0x85,chat('Owned outside whisper',4,identities[0]['character_name'],uids[0]));await poll(0)
        mark=len(peers[2].received)
        await action(0,0x5b4,b'\1'+wire.wstring('OwnedChanged')+wire.wstring('')+struct.pack('>H',690))
        await poll(2)
        changed=[e for e in peers[2].received[mark:]if e.kind==0x262]
        assert all(any(e.payload[4:12]==struct.pack('>Q',uid)and e.payload[-5:-1]==struct.pack('>i',690)for e in changed)for uid in uids[:2])
        report['checks'].append('Studio chat remains room-local; cross-scene whisper and both members friend map changes are delivered')
        await action(0,0x67,leave)
        await action(1,0x5b4,b'\1'+wire.wstring('OwnedPromoted')+wire.wstring('')+struct.pack('>H',689))
        await action(1,0x67,leave)
        from els_server.domain.town_travel import catalog
        for index in(0,1):
            await action(index,0x225,struct.pack('>iB',20001,0))
            await action(index,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
        after=snapshot()
        assert [a['location']for a in after]==[a['location']for a in before]
        assert [a['money']for a in after]==[a['money']for a in before]
        report['checks'].append('Host exit promotes an existing member; both return normally with no location or economic reward change')
        await action(0,0x923,struct.pack('>Qi3fB',0,26000,0.,0.,0.,1))
        from els_server.protocol.housing_layout_messages import encode,REQUEST
        await action(0,0x935,encode(REQUEST,([],[],[],0,0,0)))
        await action(0,0x225,struct.pack('>iB',20001,0))
        await action(0,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
        assert snapshot()==after
        report['checks'].append('Existing licensed own-house admission and layout writer save and return without changing the saved town or assets')
        coupon=next(i for i in after[0]['items']if i['template']==81650)
        await action(0,0x219,struct.pack('>QQiiIB',coupon['uid'],0,0,0,0,0))
        current=snapshot()
        assert any(t['title']==10970 for t in current[0]['titles'])
        assert all(i['uid']!=coupon['uid']for i in current[0]['items'])
        assert current[0]['money']['ed']==after[0]['money']['ed']
        report['checks'].append('Current owned title coupon uses native219, consumes its UID once and persists the source-backed title without ED change')
        item=next(i for i in after[0]['items']if i['template']==77000)
        await action(0,0x1cf,mail_request(identities[2]['character_name'],item['uid'],item['count']))
        current=snapshot();mid=next(r['id']for r in current[2]['mails']if r['claimed_at']is None)
        await action(2,0x1d2,struct.pack('>Q',mid))
        body=struct.pack('>IQ',1,mid)+bytes(6)
        for _ in range(2):await action(2,0x1d4,body)
        delivered=snapshot();moved=next(i for i in delivered[2]['items']if i['uid']==item['uid'])
        assert moved==item and all(i['uid']!=item['uid']for i in delivered[0]['items'])
        report['checks'].append('Normal native attachment send/read/claim retains UID and data; repeated claim gives no duplicate')
        pet_receipt=await qualify_pet_gems(peers[0],snapshot,report)
        trade_receipt=await qualify_personal_trade(peers,uids,snapshot,report,pet_receipt['tradable'])
        ice_receipt=await qualify_ice_decomposition(peers[0],snapshot,report)
        delivered=snapshot()
        old=peers[0];await old.close();peers.remove(old);fresh=await connect(identities[0],peers)
        old=peers[0];await old.close();peers.remove(old);await connect(identities[1],peers)
        start=len(fresh.received);await fresh.query(0x5ac,struct.pack('>iH',1,65535))
        opened=[e for e in fresh.received[start:]if e.kind==0x5ba]
        assert opened
        n=struct.unpack_from('>I',opened[-1].payload)[0]
        assert 1052 in{struct.unpack_from('>i',opened[-1].payload,4+4*i)[0]for i in range(n)}
        assert snapshot()==delivered
        report['checks'].append('Cold authenticated reconnect restores the owner background, remaining ticket and current mail/asset state')
        verify_ice_cold(snapshot,ice_receipt,report)
        verify_pet_and_trade_cold(snapshot,pet_receipt,trade_receipt,report)
        report['ok']=True
    finally:
        for _,writer in relays:writer.close();await writer.wait_closed()
        for p in reversed(peers):await p.close()


def _ice_shards(rows):
    return [sum(i['count'] for i in row['items'] if i['template'] == 130047) for row in rows]


def _ice_rewards(payload):
    # Existing inventory_management_messages.decompose_ack / original22793A0:
    # signed result, profession flag, vector<pair<template,quantity>>, records,
    # profession XP and bonus-vector. The original reader is run separately
    # against the entire observed ACK in the independent TLS qualification.
    assert len(payload) >= 9 and payload[4] == 0
    result, = struct.unpack_from('>i', payload)
    count, = struct.unpack_from('>I', payload, 5)
    assert len(payload) >= 9 + 8 * count
    values = [struct.unpack_from('>ii', payload, 9 + 8 * i) for i in range(count)]
    assert len({t for t, _ in values}) == count
    return result, dict(values)


async def qualify_ice_decomposition(peer, snapshot, report):
    before = snapshot()
    assert len(before) == 3
    item, = (i for i in before[0]['items'] if i['template'] == 800018)
    assert (item['metadata'], item['group'], item['count']) == (0, 27, 1)
    assert not item.get('sealed') and not item.get('lock_until') and 'expires_at' not in item
    body = struct.pack('>IQB', 1, item['uid'], 0)
    answer = await peer.query(0x1c0, body, 0x1c1)
    assert _ice_rewards(answer.payload) == (0, {130047: 45})
    after = snapshot()
    expected = _ice_shards(before)
    expected[0] += 45
    assert _ice_shards(after) == expected
    assert not any(i['uid'] == item['uid'] for i in after[0]['items'])
    assert after[1:] == before[1:]
    assert after[0]['money'] == before[0]['money']
    remaining = lambda row: [i for i in row['items'] if i['uid'] != item['uid'] and i['template'] != 130047]
    assert remaining(after[0]) == remaining(before[0])
    # A new transport sequence creates a NEW operation. Reusing a consumed
    # instance must fail, rather than be labelled a committed-operation replay.
    # Actual same-operation replay is already covered by the frozen SQL tests.
    retried = await peer.query(0x1c0, body, 0x1c1)
    assert _ice_rewards(retried.payload) == (-1, {})
    assert snapshot() == after
    report['checks'].append('Native1C0/1C1 consumes one owned role1 ice costume and grants exactly45 unidentified El Shards; ED/EXP and the other two owners stay unchanged; a fresh-sequence repeat of the consumed UID is refused without extra reward')
    report['ice_decomposition'] = dict(template=800018, reward_template=130047, reward_delta=45,
        repeated_consumed_uid_result=-1, same_operation_replay_exercised=False,
        ack_sha256=hashlib.sha256(answer.payload).hexdigest(), cold_authenticated_reconnect=False)
    return dict(owner=before[0]['uid'], consumed=item['uid'], totals=expected,
                ack=answer.payload, repeated_ack=retried.payload)


def verify_ice_cold(snapshot, receipt, report):
    rows = snapshot()
    assert rows[0]['uid'] == receipt['owner']
    assert _ice_shards(rows) == receipt['totals']
    assert not any(i['uid'] == receipt['consumed'] for i in rows[0]['items'])
    report['ice_decomposition']['cold_authenticated_reconnect'] = True
    report['checks'].append('Cold authenticated reconnect retains the committed45 El Shards and does not resurrect the consumed ice costume')
