"""Real authenticated duel requests; HP/control readiness are labelled fixtures."""
import asyncio,json,ssl,struct,uuid
from native_peer import connect
from els_server.domain.pvp_support import SOURCE_SHA
from els_server.friends_relay import read_packet
from els_server.protocol.social_messages import wstring as ws

async def action(p,kind,body=b'',reply=None,success=True):
    answer=await p.query(kind,body,reply)
    assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload[:20].hex())
    return answer

async def enter(p):
    await action(p,0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000))
    await action(p,0x504,struct.pack('>fffBH',0.,0.,0.,0,0))

async def leave(p):
    await action(p,0x4fe);await town(p)

async def town(p):
    from els_server.domain.town_travel import catalog
    await action(p,0x225,struct.pack('>iB',20001,0))
    await action(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))

class SupportFixture:
    """Use the authenticated control protocol, without an injected App object."""
    def __init__(self):self.writer=None;self.tasks=[]
    async def open(self,p):
        self.reader,self.writer=await p.bridge.remote('relay')
        assert p.bridge.relay_control_active and p.bridge.pvp_support_version==1
        self.ack=asyncio.get_running_loop().create_future();self.nonce=uuid.uuid4().bytes[:8]
        async def receive():
            while True:
                packet=await read_packet(self.reader)
                if packet==b'\4'+self.nonce and not self.ack.done():self.ack.set_result(True)
        async def heartbeat():
            while True:
                await self.send(b'\3'+self.nonce);await asyncio.sleep(1)
        self.reader_task=asyncio.create_task(receive());self.tasks.append(self.reader_task)
        try:
            await self.send(b'\7'+json.dumps(dict(version=1,ready=True,epoch=str(uuid.uuid4()),source_sha256=SOURCE_SHA),separators=(',',':')).encode())
            await self.send(b'\3'+self.nonce)
            async with asyncio.timeout(10):await self.ack
        except BaseException:await self.close();raise
        self.heartbeat_task=asyncio.create_task(heartbeat());self.tasks.append(self.heartbeat_task)
        self.check();return self
    async def send(self,packet):
        self.writer.write(struct.pack('>I',len(packet))+packet);await self.writer.drain()
    def check(self):
        for t in self.tasks:
            if t.done():t.result();raise AssertionError('Owned control fixture ended')
    async def close(self):
        for t in self.tasks:t.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        if self.writer is None:return
        self.writer.close()
        try:await self.writer.wait_closed()
        except ssl.SSLError as error:
            if error.reason!='APPLICATION_DATA_AFTER_CLOSE_NOTIFY':raise
        except ConnectionError:pass

async def observed(p,kind,start):
    return next((e for e in p.received[start:]if e.kind==kind),None)or await p.until(kind)

def assets(rows):
    return[{k:r[k]for k in('items','money','location','quests','official')}for r in rows]

async def scenario(identities,snapshot,report,unused_leave):
    peers=[];controls=[]
    report['HP_and_readiness']='Explicit protocol QA fixtures; actual native client qualification is separate'
    try:
        for value in identities:await connect(value,peers)
        master,refuser,guest=peers;uid=[v['uid']for v in identities]
        async def invite(a,b,expected=0):
            start=len(peers[b].received)
            answer=await peers[a].query(0x5c6,struct.pack('>QIQI',uid[a],0,uid[b],0)+ws(identities[a]['character_name'])+bytes(9))
            assert struct.unpack('>iQ',answer.payload)==(expected,uid[b])
            if expected:return None
            incoming=await observed(peers[b],0x5c8,start);offset=28+struct.unpack_from('>I',incoming.payload,24)[0]
            return incoming.payload[offset:-5]
        async def answer(a,b,full,decision):
            await peers[b].send(0x5c9,struct.pack('>QQi',uid[a],uid[b],decision)+full+bytes(8))
        full=await invite(0,1);start=len(master.received);await answer(0,1,full,1)
        assert struct.unpack_from('>i',(await observed(master,0x5ca,start)).payload)[0]==1679
        await invite(0,1,1680);saved=snapshot()[0]['refusals'];assert len(saved)==1
        report['checks'].append('Actual manual refusal persists600s pair cooldown and denies a subsequent invitation')
        for p in(master,guest):controls.append(await SupportFixture().open(p))
        report['checks'].append('Both real authenticated control channels deliver the labelled HP-readiness fixture before acceptance')
        async def battle(guild):
            before=snapshot();baseline=assets(before);count=len(before[0]['duels'])
            full=await invite(0,2);starts=[len(p.received)for p in(master,guest)];await answer(0,2,full,0)
            for p,start in zip((master,guest),starts):await observed(p,0x34b,start)
            await master.send(0x5cb,b'\1');await master.query(0x48d,reply=0x48f)
            if guild:
                for p in(master,guest):await p.send(0x828,struct.pack('>fff',0.,0.,0.))
            starts=[len(p.received)for p in(master,guest)]
            for p in(master,guest):await action(p,0x91,struct.pack('>ii',100,0))
            for p,start in zip((master,guest),starts):await observed(p,0x96,start)
            starts=[len(p.received)for p in(master,guest)]
            if guild:
                await action(master,0x6a,reply=0x6b);await observed(master,0x6c,starts[0])
            else:
                await action(master,0xa7,struct.pack('>iQQBffi?',-1,uid[2],uid[2],0,0.,0.,-1,False))
                await master.send(0xaa)
                for p,start in zip((master,guest),starts):await observed(p,0x9d,start)
                for p,hp in((master,0.),(guest,23456.)):await action(p,0x9e,struct.pack('>f',hp)+bytes(178))
            for p,start in zip((master,guest),starts):
                result=await observed(p,0xc2,start)
                for i in(0,1):
                    row=struct.unpack_from('>Q8iB',result.payload,23+i*448)
                    assert row[5:7]==(0,0)and row[8]==0
            if guild:
                await action(guest,0x6a,reply=0x6b);await observed(guest,0x6c,starts[1])
                for p in(master,guest):await enter(p)
            else:
                await action(guest,0x9e,struct.pack('>f',23456.)+bytes(178))
                for p in(master,guest):await town(p)
            after=snapshot();assert assets(after)==baseline and len(after[0]['duels'])==count+1
            for row in after[0]['duels'][-1]['rows']:assert(row['rating_delta'],row['ap_delta'],row['awarded_exp'])==(0,0,0)
            assert after[0]['refusals']==saved
            for fixture in controls:fixture.check()
            report['checks'].append(('GuildAgit6A/6B/6C'if guild else'TownA7/AA/9E/C2/replay')+' returns both real actors; exactly one result; no AP/EXP/ED/quest/official-profile or inventory changes')
        await battle(False)
        await action(master,0xea,struct.pack('>BHIiii',0,0,1,110845,1,10018))
        ticket=next(i for i in snapshot()[0]['items']if i['template']==110845)
        await action(master,0x276,struct.pack('>Q',ticket['uid'])+ws('QADuel'+str(uid[0]))+ws(''))
        guild=snapshot()[0]['guild']['id']
        await action(master,0x285,ws(identities[2]['character_name'])+struct.pack('>Q',uid[2]));await guest.until(0x287)
        await action(guest,0x288,struct.pack('>i',guild)+ws(identities[0]['character_name'])+bytes(4))
        await enter(master);await enter(guest);await invite(1,0,1678)
        report['checks'].append('Actual ticket purchase/create/invite/accept and4FB/504 enter one GuildAgit; a Town outsider cannot challenge it')
        await battle(True)
        for p in(master,guest):await leave(p)
        report['ok']=True
    finally:
        for fixture in reversed(controls):await fixture.close()
        for p in reversed(peers):await p.close()
