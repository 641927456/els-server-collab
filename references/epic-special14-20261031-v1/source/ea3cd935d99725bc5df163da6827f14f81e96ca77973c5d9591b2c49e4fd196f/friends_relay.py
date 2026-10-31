"""Bounded authenticated UDP tunnel over the existing TLS listener.

Native datagrams are opaque. Account/room/recipient authorization is checked
outside those datagrams; a supplied sender UID can never select an identity.
This tunnel is deliberately separate from native TCP encryption and sequencing.
"""
import asyncio,json,struct,time,uuid

MAX_DATAGRAM=65507
MAX_FRAME=1+24+MAX_DATAGRAM
HEARTBEAT_INTERVAL=5.0
HEARTBEAT_TIMEOUT=30.0
RECONNECT_ATTEMPTS=5
RECONNECT_WINDOW=40.0
RECONNECT_DELAY=.25
RELAY_READY_TIMEOUT=10.0


class RelayBusyError(ValueError):
    pass


class RelayUnavailableError(ConnectionError):
    pass


async def read_packet(reader):
    size=struct.unpack('>I',await reader.readexactly(4))[0]
    if not 1<=size<=MAX_FRAME:raise ValueError('Relay frame bound')
    return await asyncio.wait_for(reader.readexactly(size),10)


def data_packet(epoch,uid,data):
    if not 1<=len(data)<=MAX_DATAGRAM:raise ValueError('Relay datagram bound')
    return b'\2'+uuid.UUID(epoch).bytes+struct.pack('>Q',uid)+data


def read_data(packet):
    if not 26<=len(packet)<=MAX_FRAME or packet[0]!=2:raise ValueError('Relay packet type/size')
    return str(uuid.UUID(bytes=packet[1:17])),struct.unpack_from('>Q',packet,17)[0],packet[25:]


class PacketQueue:
    def __init__(self):self.queue=asyncio.Queue(128);self.bytes=0
    def put(self,data):
        if self.bytes+len(data)>256*1024 or self.queue.full():raise ValueError('Relay consumer too slow')
        self.queue.put_nowait(data);self.bytes+=len(data)
    async def get(self):
        data=await self.queue.get();self.bytes-=len(data);return data


class Rate:
    def __init__(self):self.at=time.monotonic();self.packets=256.;self.bytes=65536.
    def accept(self,size):
        now=time.monotonic();elapsed=now-self.at;self.at=now
        self.packets=min(256.,self.packets+elapsed*256)
        self.bytes=min(65536.,self.bytes+elapsed*65536)
        if self.packets<1 or self.bytes<size:return False
        self.packets-=1;self.bytes-=size;return True


async def write_loop(writer,queue):
    while True:
        packet=await queue.get();writer.write(struct.pack('>I',len(packet))+packet)
        await asyncio.wait_for(writer.drain(),10)


class RelayServer:
    def __init__(self,application,log=lambda *a,**kw:None):self.app=application;self.endpoints={};self.log=log

    async def serve(self,reader,writer,identity,control=False):
        account_id=identity['id']
        if account_id in self.endpoints:
            if control:
                packet=b'\5'+b'{"code":"relay_busy"}'
                writer.write(struct.pack('>I',len(packet))+packet)
                await asyncio.wait_for(writer.drain(),10)
            raise RelayBusyError('Relay already connected')
        queue=PacketQueue();self.endpoints[account_id]=queue;rate=Rate()
        self.log('relay_opened',account_id=account_id,control=control)
        dungeons=self.app.world.dungeons
        async def monitor():
            previous=object()
            while True:
                manifest=await self.app.call(dungeons.manifest,self.app,account_id)
                if manifest!=previous:
                    queue.put(b'\1'+json.dumps(manifest,separators=(',',':')).encode());previous=manifest
                await asyncio.sleep(.1)
        async def receive():
            while True:
                packet=await asyncio.wait_for(read_packet(reader),HEARTBEAT_TIMEOUT) if control else await read_packet(reader)
                if control and packet[:1]==b'\3':
                    if len(packet)!=9:raise ValueError('Relay heartbeat size')
                    if not rate.accept(len(packet)):raise ValueError('Relay rate bound')
                    queue.put(b'\4'+packet[1:]);continue
                if control and packet==b'\6':return
                if control and packet[:1]==b'\7':
                    if len(packet)>1024 or not rate.accept(len(packet)):raise ValueError('PvP support relay status bound')
                    await self.app.call(self.app.world.pvp.support_status,self.app,account_id,queue,json.loads(packet[1:]))
                    continue
                epoch,target,data=read_data(packet)
                if not rate.accept(len(data)):raise ValueError('Relay rate bound')
                route=await self.app.call(dungeons.relay_target,self.app,account_id,epoch,target)
                if route is None:continue
                target_id,sender_uid=route;destination=self.endpoints.get(target_id)
                if destination is not None:destination.put(data_packet(epoch,sender_uid,data))
        tasks=[asyncio.create_task(write_loop(writer,queue)),asyncio.create_task(monitor()),asyncio.create_task(receive())]
        try:
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
        except TimeoutError:
            self.log('relay_heartbeat_timeout',account_id=account_id)
            raise
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            try:
                await self.app.call(self.app.world.pvp.support_lost,account_id,queue)
                await self.app.call(dungeons.relay_lost,self.app,account_id)
            finally:
                # Do not admit a replacement while the old relay_lost callback
                # can still abort that replacement's newly started dungeon.
                if self.endpoints.get(account_id) is queue:self.endpoints.pop(account_id)
                self.log('relay_closed',account_id=account_id)


class Proxy(asyncio.DatagramProtocol):
    def __init__(self,owner,uid):
        self.owner=owner;self.uid=uid;self.transport=None
        self.closed=asyncio.get_running_loop().create_future()
    def connection_made(self,transport):self.transport=transport
    def connection_lost(self,error):
        if not self.closed.done():self.closed.set_result(None)
    def datagram_received(self,data,address):
        o=self.owner
        if o.manifest is None or address!=o.bridge.game_address or not 1<=len(data)<=MAX_DATAGRAM:return
        try:o.outgoing.put(data_packet(o.manifest['epoch'],self.uid,data))
        except ValueError:o.fail('Local combat relay queue overflow')


class RelayClient:
    def __init__(self,bridge,reconnect=False):
        self.bridge=bridge;self.manifest=None;self.proxies={};self.outgoing=PacketQueue()
        self.failure=None;self.failed=asyncio.Event();self.task=None
        self.ready=asyncio.Event()
        self.reconnect=reconnect;self.ever_ready=False;self.connected_at=None
        self.recovering=False

    def fail(self,reason):self.failure=reason;self.failed.set()

    async def configure(self,value):
        if value is not None:
            if not isinstance(value,dict) or set(value)!={'epoch','uid','peers'}:raise ValueError('Relay manifest')
            uuid.UUID(value['epoch'])
            peers=value['peers']
            if (not isinstance(peers,list) or not 1<=len(peers)<=6
                or any(set(p)!={'uid','port'} or type(p['uid']) is not int or not 0<p['uid']<2**63
                       or type(p['port']) is not int or p['port']!=21100+i for i,p in enumerate(peers))
                or len({p['uid'] for p in peers})!=len(peers) or value['uid'] not in {p['uid'] for p in peers}):raise ValueError('Relay peer roster')
        previous=list(self.proxies.values())
        for transport,_ in previous:transport.close()
        if previous:await asyncio.gather(*(protocol.closed for _,protocol in previous))
        self.proxies.clear();self.manifest=None
        if value is None:return
        try:
            for peer in value['peers']:
                if peer['uid']==value['uid']:continue
                pair=await asyncio.get_running_loop().create_datagram_endpoint(lambda uid=peer['uid']:Proxy(self,uid),local_addr=('127.0.0.1',peer['port']))
                self.proxies[peer['uid']]=pair
            self.manifest=value
        except BaseException:
            for transport,_ in self.proxies.values():transport.close()
            self.proxies.clear();raise

    async def run(self):
        if not self.reconnect:return await self._run_once()
        attempts=0;recovery_started=None
        while not self.bridge.closing:
            try:
                await self._run_once()
                raise ConnectionError('Relay stream ended')
            except (asyncio.IncompleteReadError,ConnectionError,OSError,TimeoutError,RelayBusyError) as error:
                if not self.ever_ready:raise
                now=time.monotonic()
                if recovery_started is None or (self.connected_at is not None and now-self.connected_at>=HEARTBEAT_TIMEOUT):
                    attempts=0;recovery_started=now
                attempts+=1;self.connected_at=None;self.ready.clear();self.recovering=True
                self.bridge.log('relay_connection_lost',reason=type(error).__name__,attempt=attempts)
                if attempts>RECONNECT_ATTEMPTS or now-recovery_started>=RECONNECT_WINDOW:
                    raise RelayUnavailableError('Relay reconnect budget exhausted') from None
                # The old run has fully closed its sockets and room proxies.
                # Never replay queued datagrams or native/business requests.
                self.outgoing=PacketQueue();self.failure=None;self.failed=asyncio.Event()
                await asyncio.sleep(min(2.0,RECONNECT_DELAY*2**(attempts-1)))
                self.bridge.log('relay_reconnecting',attempt=attempts)

    async def _run_once(self):
        writer=None;tasks=[];control=False
        try:
            reader,writer=await self.bridge.remote(role='relay')
            control=getattr(self.bridge,'relay_control_active',False)
            if control and self.bridge.pvp_support_version==1:
                self.outgoing.put(b'\7'+json.dumps(self.bridge.pvp_support,separators=(',',':')).encode())
            pending={};last_pong=time.monotonic();counter=0;ready_deadline=time.monotonic()+RELAY_READY_TIMEOUT
            async def heartbeat():
                nonlocal counter
                while True:
                    if time.monotonic()-last_pong>=HEARTBEAT_TIMEOUT:raise TimeoutError('Relay heartbeat acknowledgement timed out')
                    now=time.monotonic()
                    for old,created in list(pending.items()):
                        if now-created>=HEARTBEAT_TIMEOUT:pending.pop(old)
                    counter+=1;nonce=struct.pack('>Q',counter);pending[nonce]=now
                    self.outgoing.put(b'\3'+nonce)
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
            async def receive():
                nonlocal last_pong
                while True:
                    if not self.ready.is_set():
                        packet=await asyncio.wait_for(read_packet(reader),max(.001,ready_deadline-time.monotonic()))
                    else:packet=await read_packet(reader)
                    if control and packet[:1]==b'\4':
                        if len(packet)!=9:raise ValueError('Unexpected relay heartbeat acknowledgement')
                        sequence=struct.unpack('>Q',packet[1:])[0]
                        if not 1<=sequence<=counter:raise ValueError('Unexpected relay heartbeat acknowledgement')
                        created=pending.pop(packet[1:],None);now=time.monotonic()
                        # Issued but expired/duplicate ACKs never renew liveness.
                        # Check age here as well as in the periodic prune loop.
                        if created is None or now-created>=HEARTBEAT_TIMEOUT:continue
                        last_pong=now;continue
                    if control and packet[:1]==b'\5':
                        if packet[1:]!=b'{"code":"relay_busy"}':raise ValueError('Unknown relay rejection')
                        raise RelayBusyError('Relay already connected')
                    if packet[0]==1:
                        if len(packet)>4096:raise ValueError('Relay manifest bound')
                        await self.configure(json.loads(packet[1:]))
                        if not self.ready.is_set():
                            self.ever_ready=True;self.connected_at=time.monotonic()
                            if self.recovering:
                                self.bridge.log('relay_reconnected',control=control)
                                self.recovering=False
                        self.ready.set()
                    else:
                        epoch,sender,data=read_data(packet)
                        if self.manifest and epoch==self.manifest['epoch'] and sender in self.proxies and self.bridge.game_address:
                            self.proxies[sender][0].sendto(data,self.bridge.game_address)
            tasks=[asyncio.create_task(write_loop(writer,self.outgoing)),asyncio.create_task(receive()),asyncio.create_task(self.failed.wait())]
            if control:tasks.append(asyncio.create_task(heartbeat()))
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
            if self.failure:raise ValueError(self.failure)
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            await self.configure(None)
            if writer:
                if control and self.ready.is_set():
                    try:
                        writer.write(struct.pack('>I',1)+b'\6')
                        await asyncio.wait_for(writer.drain(),1)
                    except (ConnectionError,OSError,TimeoutError):pass
                writer.close()
                try:await asyncio.wait_for(writer.wait_closed(),5)
                except (ConnectionError,OSError,TimeoutError):pass
