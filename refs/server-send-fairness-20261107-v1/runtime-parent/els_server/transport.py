"""Bounded asyncio TCP service using the verified native wire codec."""
import asyncio
import time
from els_server.performance import capture_calls
import secrets
import json
import struct
import ssl
from els_server.protocol.protocol_codec import (BOOTSTRAP_KEYS,Keys,Event,ProtocolError,
    encode_event,encode_frame,welcome_event)
from els_server.protocol.frame_encoder import FrameEncoder
from els_server.domain.local_session import SessionOrderError
from els_server.port_probe import PortProbe
from els_server.dungeon34320_observation import Trace34320


class GameServer:
    def __init__(self,config,application,log):
        self.config=config;self.application=application;self.log=log
        self.listener=None;self.connections={};self.next_id=0;self.closing=False
        self.probe_transport=None;self.probe_protocol=None;self.probe_port=None
        self.local_sessions=set()
        from els_server.periodic_scheduler import PeriodicScheduler
        self.periodics=PeriodicScheduler(application,.05,log)
        self.metrics=dict(accepted=0,rejected=0,closed=0,protocol_errors=0,requests=0,responses=0,auxiliary_coalesced=0,town_moves_coalesced=0)
        from els_server.accounts_gateway import AccountGateway
        self.account_gateway=AccountGateway(config,application)
        from els_server.diagnostic_reports import UploadService
        self.diagnostics=UploadService(config.state_file.parent/'diagnostics')
        from els_server.friends_relay import RelayServer
        self.relay=RelayServer(application,log)
        self.realtime=None
        self.admission_path=config.accounts_file.with_name('maintenance-admission.json')
        self._maintenance_accounts=None

    async def start(self):
        # Bind first, advertise the actual port in 1B only after both services
        # are ready. An ephemeral loopback port avoids cross-instance conflicts.
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(self.config.tls_cert,self.config.tls_key)
        self.probe_port=self.config.client_probe_port
        try:
            self._load_maintenance_admission()
            from els_server.realtime import RealtimeAccess
            self.realtime=RealtimeAccess(self.application,self.log)
            await self.realtime.start();self.relay.realtime=self.realtime
            self.listener=await asyncio.start_server(self.accept,self.config.host,self.config.port,
                                                    limit=65536,backlog=self.config.max_connections,
                                                    **({'ssl':tls,'ssl_handshake_timeout':self.config.authentication_timeout} if tls else {}))
        except BaseException:
            if self.realtime is not None:
                await self.realtime.close();self.realtime=None;self.relay.realtime=None
            if self.probe_transport:self.probe_transport.close();await self.probe_protocol.closed
            raise
        address=self.listener.sockets[0].getsockname()
        self.log('listening',address=list(address),profile=self.config.profile,probe_port=self.probe_port)
        self.diagnostics.start()
        return address

    def _load_maintenance_admission(self):
        # Publisher-owned startup policy; original credential checks stay fresh.
        self._maintenance_accounts=None
        try:raw=self.admission_path.read_bytes()
        except FileNotFoundError:return
        policy=json.loads(raw)
        if (type(policy)is not dict or set(policy)!={'owner','allowed_account_ids'}
                or type(policy['owner'])is not str or not policy['owner']
                or type(policy['allowed_account_ids'])is not list or not policy['allowed_account_ids']
                or any(type(uid)is not int or uid<=0 for uid in policy['allowed_account_ids'])):
            raise ValueError('Invalid maintenance admission policy')
        self._maintenance_accounts=frozenset(policy['allowed_account_ids'])

    def _check_maintenance_admission(self,identity):
        if self._maintenance_accounts is None:return
        try:self.admission_path.stat()
        except FileNotFoundError:
            self._maintenance_accounts=None
            return
        if identity['id']not in self._maintenance_accounts:
            raise ValueError('Server maintenance')

    def local_bootstrap_allowed(self,uid):
        return (not self.closing and self.config.mode=='local' and any(
            s.account.uid==uid and s.role=='game' and s.enter_dungeon
            and s.phase in ('dungeon_loading','dungeon_active')
            and not s.dungeon_return_pending for s in self.local_sessions))

    def accept(self,reader,writer):
        if self.closing or len(self.connections)>=self.config.max_connections:
            self.metrics['rejected']+=1;writer.close()
            self.log('connection_rejected',reason='concurrent_limit' if not self.closing else 'shutdown')
            return
        self.next_id+=1;index=self.next_id
        task=asyncio.create_task(self.handle(reader,writer,index),name=f'connection-{index}')
        self.connections[task]=writer;self.metrics['accepted']+=1
        def finished(task):
            self.connections.pop(task,None);self.metrics['closed']+=1
            if not task.cancelled() and task.exception():
                self.log('connection_task_error',connection=index,error=repr(task.exception()))
        task.add_done_callback(finished)

    async def read_frame(self,reader):
        # Idle peers and partial/slow frames have independent deadlines.
        first=await asyncio.wait_for(reader.readexactly(1),self.config.idle_timeout)
        async with asyncio.timeout(self.config.frame_timeout):
            header=first+await reader.readexactly(7)
            length=struct.unpack_from('<I',header)[0]
            if not 40<=length<=1024*1024:raise ProtocolError('Invalid frame length')
            return header+await reader.readexactly(length-8)

    async def handle(self,reader,writer,index):
        notifications=None;clock=None;closure=None;business=None;native_sources=None;inbox=None;encoder=None
        self.log('accepted',connection=index)
        try:
            identity=None;role=None;diagnostic_auth=None;relay_control=False
            from els_server.friends_wire import read_json,write_json
            async with asyncio.timeout(self.config.authentication_timeout):
                try:
                    auth=await read_json(reader)
                    if auth.get('op')=='diagnostic_upload':
                        diagnostic_auth=auth
                    elif 'op' in auth:
                        peer=writer.get_extra_info('peername')
                        if auth.get('op') in ('tutorial_recovery_preview','tutorial_recovery_confirm'):
                            reply=await self.account_gateway.recovery(auth,peer[0] if peer else '')
                        else:
                            reply=await self.account_gateway.request(auth,peer[0] if peer else '')
                        await write_json(writer,reply)
                        return
                    if diagnostic_auth is None:
                        if set(auth) not in ({'name','token'},{'name','token','role'},{'name','token','role','relay_control_version'}):raise ValueError('Authentication fields')
                        role=auth.get('role')
                        if 'role' in auth and role!='relay':raise ValueError('Authentication role')
                        if 'relay_control_version' in auth:
                            if role!='relay' or type(auth['relay_control_version']) is not int or auth['relay_control_version']!=1:raise ValueError('Relay control version')
                            relay_control=True
                        identity=await self.application.call(self.application.registry.authenticate,auth['name'],auth['token'])
                        self._check_maintenance_admission(identity)
                except (ValueError,UnicodeError):
                    self.log('authentication_rejected',connection=index)
                    await write_json(writer,{'ok':False});return
                finally:
                    if 'auth' in locals():del auth
                if diagnostic_auth is None:
                    await write_json(writer,{'ok':True,'account_id':identity['id'],'probe_port':self.probe_port,'relay_version':1,'relay_control_version':1,'pvp_support_version':1})
                    self.log('authenticated',connection=index,account_id=identity['id'],role=role or 'native')
            if diagnostic_auth is not None:
                # ZIP transfer has its own bounded deadline, outside the
                # short native authentication deadline. No game session.
                peer=writer.get_extra_info('peername')
                try:
                    reply=await self.diagnostics.handle(self.application,reader,writer,diagnostic_auth,peer[0] if peer else '')
                    if reply and reply.get('ok'):self.log('diagnostic_uploaded',connection=index,report_id=reply['report_id'])
                finally:diagnostic_auth.clear()
                return
            if role=='relay':
                try:await self.relay.serve(reader,writer,identity,control=relay_control)
                except ValueError as error:raise ProtocolError(str(error)) from error
                return
            business=await self.application.session(port_probe_port=self.probe_port,identity=identity)
            from els_server.domain.native_session_sources import attach as attach_native_sources
            native_sources=attach_native_sources(business)
            keys=Keys(secrets.token_bytes(8),secrets.token_bytes(8));spi=secrets.randbelow(65535)+1
            encoder=FrameEncoder(keys)
            outgoing=2;heartbeat_sent=False
            operation=asyncio.Lock();wire_lock=asyncio.Lock();clock_epoch=None;town_epoch=None
            if self.realtime is not None:
                business._realtime_clock=True
                async def peer_closed():
                    try:await writer.wait_closed()
                    except OSError:pass
                    finally:self.realtime.close_session(business)
                closure=asyncio.create_task(peer_closed(),name=f'realtime-close-{index}')
            memory1_diagnostic_count=0
            dungeon34320_trace=Trace34320(self.log,index)
            async def write(wire):
                writer.write(wire)
                await asyncio.wait_for(writer.drain(),self.config.write_timeout)
            async def send(messages, *, send_path='request_reply', request_sequence=None, request_kind=None, timing=None):
                nonlocal outgoing,clock_epoch,town_epoch
                messages=tuple(messages)
                entered=(business.shop_session_id,business.account.uid,business.active_map)if any(m.kind==0x228 and m.payload[:4]==bytes(4)for m in messages)else None
                async with wire_lock:
                    wires=[];sent=[];size=0
                    async def flush():
                        nonlocal clock_epoch,town_epoch,size
                        if not wires:return
                        started=time.perf_counter()
                        try:await write(b''.join(wires))
                        finally:
                            if timing is not None:timing['send_ms']+=(time.perf_counter()-started)*1000
                        positions=[]
                        for message,wire_sequence,length in sent:
                            if(message.kind in(0x14a,0xb2)
                                or message.kind in(0x29,0x226)and message.payload[:4]==bytes(4)
                                or message.kind==0x68 and business.phase!='town_ready'):town_epoch=None
                            elif message.kind==0x228 and message.payload[:4]==bytes(4):town_epoch=entered
                            if message.kind in(0x14a,0xb2,0x68):clock_epoch=None
                            elif message.kind==0xbd and self.realtime is not None:
                                # Bind the scene just sent, not a publication
                                # which may still describe the previous part.
                                from els_server.domain.dungeon_time_sync import context
                                clock_epoch=context(business)
                            dungeon34320_trace.sent(business,message,wire_sequence,send_path=send_path,
                                request_sequence=request_sequence,request_kind=request_kind)
                            self.metrics['responses']+=1
                            if(message.event_id==0x201 and message.kind==0x22e
                                    and business.phase=='town_ready'):
                                positions.append((wire_sequence,length))
                            else:self.log('local_business_response_sent',connection=index,kind=message.kind,size=length)
                        if positions:
                            self.log('town_positions_sent',connection=index,count=len(positions),
                                size=sum(length for _,length in positions),
                                first_sequence=positions[0][0],last_sequence=positions[-1][0])
                        wires.clear();sent.clear();size=0
                    for message in messages:
                        encoding=time.perf_counter()
                        wire_sequence=outgoing
                        wire=encoder.encode(encode_event(message),spi=spi,sequence=wire_sequence)
                        outgoing+=1
                        encoded=time.perf_counter()
                        if timing is not None:timing['encode_ms']+=(encoded-encoding)*1000
                        # Preserve every native frame and sequence. Flush the
                        # ready response as bounded TLS writes, without a timer.
                        wires.append(wire);sent.append((message,wire_sequence,len(wire)));size+=len(wire)
                        if size>=65536:await flush()
                    await flush()
                    if send_path in ('request_reply','periodic') and native_sources is not None:
                        native_sources.sent(messages)
            await write(encode_frame(encode_event(welcome_event(keys,spi)),BOOTSTRAP_KEYS))
            self.log('generated_welcome_sent',connection=index)
            from els_server.native_inbox import NativeInbox
            auxiliary=(lambda event:self.realtime.auxiliary(business,event))if self.realtime is not None else None
            inbox=NativeInbox(lambda:self.read_frame(reader),keys,business,self.metrics,auxiliary=auxiliary)
            async def send_periodic(messages):
                await send(messages,send_path='periodic')
            notifications=asyncio.create_task(self.periodics.serve(business,operation,send_periodic),name=f'notifications-{index}')
            # Propagate timer failures promptly even while waiting for a client packet.
            def notification_done(task):
                if not task.cancelled() and task.exception():writer.close()
            notifications.add_done_callback(notification_done)
            if self.realtime is not None:
                business._realtime_town_moves=True
                async def realtime_clock():
                    from els_server.domain.dungeon_time_sync import notification
                    next_clock=time.monotonic()+1
                    while True:
                        await asyncio.sleep(.015)
                        now=time.monotonic()
                        if now>=next_clock:
                            next_clock=now+1
                            key=self.realtime.clock(business)
                            if key is not None and key==clock_epoch:await send([notification()],send_path='realtime')
                        if town_epoch is None or wire_lock.locked()or not business.mailbox.moves:continue
                        app=self.application
                        if not self.realtime.allowed(identity['id'],app.realtime.view):continue
                        # No SQL, game-state mutation or blocking lock on the
                        # socket loop. A queued unstarted poll may keep the
                        # operation lock; its first Town action also needs
                        # world, so it cannot drain creation messages here.
                        if not app.world_lock.acquire(blocking=False):continue
                        try:
                            if (app.playing.get(identity['id'])is not business or business.released
                                    or business.role!='game'or business.phase!='town_ready'
                                    or business.social_overflow or business.coop_error
                                    or town_epoch!=(business.shop_session_id,business.account.uid,business.active_map)
                                    or self.realtime.binding(identity['id'])!=business.shop_session_id
                                    or app.world.members.get(business)!=(1,business.active_map)
                                    or app.world.dungeons.room(business)is not None
                                    or app.world.pvp.room(business)is not None
                                    or app.world.racing.room(business)is not None
                                    or app.world.field_bosses.room(business)is not None):continue
                            if operation.locked():
                                slot=next((s for s in self.periodics.slots.values()if s.session is business),None)
                                if slot is None or slot.claim is None or slot.claim.state!='pending':continue
                            box=business.mailbox
                            if not box.lock.acquire(blocking=False):continue
                            try:
                                if box.messages:continue
                                moves=box._drain()
                            finally:box.lock.release()
                        finally:app.world_lock.release()
                        # send acquires this connection's free wire lock
                        # before its first await, preserving native frame
                        # ordering ahead of a newly started business poll.
                        if moves:await send(moves,send_path='realtime')
                clock=asyncio.create_task(realtime_clock(),name=f'realtime-clock-{index}')
                clock.add_done_callback(notification_done)
            while not self.closing:
                frame=await inbox.get();event=frame.event
                entry_fields={}
                if event.event_id==0x202 and event.kind==0x7d4 and len(event.payload)==8:
                    entry_mode,dungeon=struct.unpack('>ii',event.payload)
                    entry_fields=dict(entry_mode=entry_mode,dungeon=dungeon)
                if event.event_id==0x202 and event.kind==0x58c:
                    entry_fields=dict(town_warp_payload_bytes=len(event.payload),
                        native_performers=event.performers,
                        native_sentinel_uids=event.uid==event.target_uid==2**64-1,
                        native_payload_mode=event.payload_mode)
                    if len(event.payload)==7:
                        destination,free,special,growth=struct.unpack('>i3B',event.payload)
                        entry_fields.update(town_destination=destination,warp_flags=[free,special,growth])
                if event.event_id==0x202 and event.kind==0x104:
                    entry_fields=dict(wear_payload_bytes=len(event.payload),native_performers=event.performers,
                        native_sentinel_uids=event.uid==event.target_uid==2**64-1,native_payload_mode=event.payload_mode)
                    if len(event.payload)==11:
                        sg,ss,dg,ds,flag=struct.unpack('>BiBiB',event.payload)
                        entry_fields.update(wear_source=[sg,ss],wear_destination=[dg,ds],wear_flag=flag)
                run=getattr(business,'dungeon_run',None)
                if (event.event_id==0x202 and event.kind==0xad and run is not None
                        and run.identity==35250
                        and memory1_diagnostic_count<24):
                    memory1_diagnostic_count+=1
                    from els_server.domain.dungeon_lifecycle import death_report
                    try:
                        d=death_report(event.payload)
                        entry_fields=dict(dungeon=35250,stage=run.stage,part=run.part,retirement_probe=dict(
                            index=d['index'],flag=d['flag'],source=d['source'],killer=d['killer'],
                            xyz=d['xyz'],status=d['status'],hp_bits=d['hp_bits'],last_uid=d['last_uid'],
                            extra_uid=d['extra_uid'],contribution_count=len(d['contribution']),
                            counters_count=len(d['counters']),readiness=d['readiness']))
                    except ValueError:entry_fields=dict(dungeon=35250,retirement_probe_error='malformed_AD')
                self.log('client_request',connection=index,sequence=frame.sequence,
                         event_id=event.event_id,kind=event.kind,size=frame.size,**entry_fields)
                received=frame.received
                async with self.periodics.foreground(business,operation):
                    acquired=time.perf_counter()
                    timing=dict(connection_wait_ms=(acquired-received)*1000,encode_ms=0.,send_ms=0.)
                    if event.event_id==1026 and event.kind==3392 and not heartbeat_sent:
                        await send([Event(0)],send_path='heartbeat');heartbeat_sent=True
                    before=business.phase
                    trace34320_before=dungeon34320_trace.before(business,event,frame.sequence)
                    with capture_calls() as calls:
                        try:
                            messages=await self.application.call(business.handle,event,request_sequence=frame.sequence)
                            if event.event_id==0x202 and event.kind in (0x42c,0x42f,0x542):
                                self.log('mount_diagnostic',connection=index,sequence=frame.sequence,phase=business.phase,
                                    rejection=getattr(business,'_mount_rejection',None))
                        except BaseException:
                            timing['total_ms']=(time.perf_counter()-received)*1000
                            self.log('request_timing',connection=index,sequence=frame.sequence,kind=event.kind,
                                phase=business.phase,calls=calls,failed=True,**timing)
                            raise
                    if event.event_id==0x202 and event.kind==0x104:
                        results=[struct.unpack_from('>i',m.payload,len(m.payload)-4)[0]for m in messages
                            if m.event_id==0x201 and m.kind==0x105 and len(m.payload)>=8]
                        self.log('wear_diagnostic',connection=index,sequence=frame.sequence,phase=business.phase,
                            results=results,rejection=getattr(business,'_wear_rejection',None))
                    if event.event_id==0x202 and event.kind==0x58c:
                        results=[struct.unpack_from('>i',m.payload)[0] for m in messages
                            if m.event_id==0x201 and m.kind==0x58d and len(m.payload)>=4]
                        self.log('town_warp_diagnostic',connection=index,sequence=frame.sequence,
                            phase=business.phase,results=results,
                            rejection=getattr(business,'_town_warp_rejection',None))
                    from els_server.domain.dungeon_diagnostics import refusal
                    diagnostic=refusal(business,event,messages)
                    if diagnostic is not None:
                        self.log('dungeon_refusal',connection=index,sequence=frame.sequence,**diagnostic)
                    dungeon34320_trace.after(trace34320_before,business,messages)
                    if before!=business.phase:
                        self.log('business_phase',connection=index,request=event.kind,before=before,after=business.phase)
                    timing['reply_complete']=False
                    try:
                        await send(messages,send_path='request_reply',request_sequence=frame.sequence,request_kind=event.kind,timing=timing)
                        timing['reply_complete']=True
                    finally:
                        timing['total_ms']=(time.perf_counter()-received)*1000
                        if event.kind!=0x7d0 or timing['total_ms']>=100 or frame.sequence%64==0:
                            self.log('request_timing',connection=index,sequence=frame.sequence,kind=event.kind,
                                phase=business.phase,calls=calls,**timing)
        except asyncio.IncompleteReadError:
            pass
        except (ProtocolError,SessionOrderError) as error:
            self.metrics['protocol_errors']+=1
            self.log('protocol_error',connection=index,error=str(error))
        except TimeoutError:
            self.log('connection_timeout',connection=index)
        except (ConnectionError,OSError) as error:
            self.log('connection_error',connection=index,error=type(error).__name__,
                errno=getattr(error,'errno',None),winerror=getattr(error,'winerror',None),
                ssl_library=getattr(error,'library',None),ssl_reason=getattr(error,'reason',None))
        except Exception as error:
            self.log('worker_error',connection=index,error=repr(error))
        finally:
            from els_server.cleanup import cleanup_all_async
            async def stop_clock():
                if clock:
                    clock.cancel();await asyncio.gather(clock,return_exceptions=True)
            async def stop_notifications():
                if notifications:
                    notifications.cancel()
                    results=await asyncio.gather(notifications,return_exceptions=True)
                    if results and isinstance(results[0],Exception):
                        self.log('notification_error',connection=index,error=repr(results[0]))
            def release():
                if business is not None:
                    self.local_sessions.discard(business)
                    return self.application.release(business)
            async def wait_closed():
                try:await asyncio.wait_for(writer.wait_closed(),self.config.write_timeout)
                except (OSError,TimeoutError):pass
            # Every stage runs even when an earlier close fails. Cancellation
            # waits for the whole teardown before this connection can retire.
            await cleanup_all_async(
                lambda:inbox.close() if inbox is not None else None,
                lambda:self.realtime.close_session(business) if business is not None and self.realtime is not None else None,
                stop_clock,lambda:native_sources.close() if native_sources is not None else None,
                stop_notifications,release,
                lambda:encoder.close() if encoder is not None else None,
                writer.close,wait_closed,
                lambda:asyncio.gather(closure,return_exceptions=True) if closure else None,
                lambda:self.log('connection_finished',connection=index))

    async def close(self):
        self.closing=True
        self.account_gateway.begin_close()
        from els_server.cleanup import cleanup_all_async
        async def close_probe():
            if self.probe_transport:
                self.probe_transport.close();await self.probe_protocol.closed
        async def close_connections():
            if self.listener:self.listener.close()
            tasks=list(self.connections)
            for writer in list(self.connections.values()):writer.close()
            if tasks:
                done,pending=await asyncio.wait(tasks,timeout=self.config.shutdown_timeout)
                for task in pending:task.cancel()
                if pending:await asyncio.gather(*pending,return_exceptions=True)
        async def close_listener():
            # Python 3.13 waits for active TLS peers; drain their owners first.
            if self.listener:
                try:await asyncio.wait_for(self.listener.wait_closed(),self.config.shutdown_timeout)
                except TimeoutError:self.log('listener_shutdown_timeout')
        await cleanup_all_async(close_probe,close_connections,close_listener,
            self.periodics.close,self.account_gateway.close,self.diagnostics.close,
            lambda:self.realtime.close() if self.realtime is not None else None)
        self.log('finished',**self.metrics,active=len(self.connections))
