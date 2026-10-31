"""Bounded asyncio TCP service using the verified native wire codec."""
import asyncio
import time
from els_server.performance import capture_calls
import secrets
import struct
import ssl
from els_server.protocol.protocol_codec import (BOOTSTRAP_KEYS,Keys,Event,ProtocolError,
    encode_event,encode_frame,decode_event,decode_frame,welcome_event)
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
        self.periodics=PeriodicScheduler(application,.05 if config.mode=='friends' else 1,log)
        self.metrics=dict(accepted=0,rejected=0,closed=0,protocol_errors=0,requests=0,responses=0)
        from els_server.accounts_gateway import AccountGateway
        self.account_gateway=AccountGateway(config,application)
        from els_server.diagnostic_reports import UploadService
        self.diagnostics=UploadService(config.state_file.parent/'diagnostics')
        from els_server.friends_relay import RelayServer
        self.relay=RelayServer(application,log)

    async def start(self):
        # Bind first, advertise the actual port in 1B only after both services
        # are ready. An ephemeral loopback port avoids cross-instance conflicts.
        tls=None
        if self.config.mode=='friends':
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2
            tls.load_cert_chain(self.config.tls_cert,self.config.tls_key)
            # Native UDP discovery stays at each client's loopback bridge.
            self.probe_port=self.config.client_probe_port
        else:
            self.probe_transport,self.probe_protocol=await asyncio.get_running_loop().create_datagram_endpoint(
                lambda:PortProbe(self.log,bootstrap_allowed=self.local_bootstrap_allowed),local_addr=(self.config.host,0))
            self.probe_port=self.probe_transport.get_extra_info('sockname')[1]
        try:
            self.listener=await asyncio.start_server(self.accept,self.config.host,self.config.port,
                                                    limit=65536,backlog=self.config.max_connections,
                                                    **({'ssl':tls,'ssl_handshake_timeout':self.config.authentication_timeout} if tls else {}))
        except BaseException:
            if self.probe_transport:self.probe_transport.close();await self.probe_protocol.closed
            raise
        address=self.listener.sockets[0].getsockname()
        self.log('listening',address=list(address),profile=self.config.profile,probe_port=self.probe_port)
        if self.config.mode=='friends':self.diagnostics.start()
        return address

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
        notifications=None;business=None;native_sources=None
        self.log('accepted',connection=index)
        try:
            identity=None;role=None;diagnostic_auth=None;relay_control=False
            if self.config.mode=='friends':
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
                    except (ValueError,UnicodeError):
                        self.log('authentication_rejected',connection=index)
                        await write_json(writer,{'ok':False});return
                    finally:
                        if 'auth' in locals():del auth
                    if diagnostic_auth is None:
                        await write_json(writer,{'ok':True,'account_id':identity['id'],'probe_port':self.probe_port,'relay_version':1,'relay_control_version':1})
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
            if self.config.mode=='local':self.local_sessions.add(business)
            keys=Keys(secrets.token_bytes(8),secrets.token_bytes(8));spi=secrets.randbelow(65535)+1
            outgoing=2;incoming=1;heartbeat_sent=False
            operation=asyncio.Lock()
            memory1_diagnostic_count=0
            dungeon34320_trace=Trace34320(self.log,index)
            async def write(wire):
                writer.write(wire)
                await asyncio.wait_for(writer.drain(),self.config.write_timeout)
            async def send(messages, *, send_path='request_reply', request_sequence=None, request_kind=None, timing=None):
                nonlocal outgoing
                messages=tuple(messages)
                for message in messages:
                    encoding=time.perf_counter()
                    wire_sequence=outgoing
                    wire=encode_frame(encode_event(message),keys,spi=spi,sequence=wire_sequence)
                    outgoing+=1
                    encoded=time.perf_counter()
                    if timing is not None:timing['encode_ms']+=(encoded-encoding)*1000
                    try:
                        await write(wire)
                    finally:
                        if timing is not None:timing['send_ms']+=(time.perf_counter()-encoded)*1000
                    dungeon34320_trace.sent(business,message,wire_sequence,send_path=send_path,
                        request_sequence=request_sequence,request_kind=request_kind)
                    self.metrics['responses']+=1
                    # Payloads and session keys belong only in the explicit capture tool.
                    self.log('local_business_response_sent',connection=index,kind=message.kind,size=len(wire))
                if send_path in ('request_reply','periodic') and native_sources is not None:
                    native_sources.sent(messages)
            await write(encode_frame(encode_event(welcome_event(keys,spi)),BOOTSTRAP_KEYS))
            self.log('generated_welcome_sent',connection=index)
            async def send_periodic(messages):
                await send(messages,send_path='periodic')
            notifications=asyncio.create_task(self.periodics.serve(business,operation,send_periodic),name=f'notifications-{index}')
            # Propagate timer failures promptly even while waiting for a client packet.
            def notification_done(task):
                if not task.cancelled() and task.exception():writer.close()
            notifications.add_done_callback(notification_done)
            while not self.closing:
                wire=await self.read_frame(reader)
                frame=decode_frame(wire,keys,expected_sequence=incoming);incoming+=1
                event=decode_event(frame.plaintext);self.metrics['requests']+=1
                entry_fields={}
                if event.event_id==0x202 and event.kind==0x7d4 and len(event.payload)==8:
                    entry_mode,dungeon=struct.unpack('>ii',event.payload)
                    entry_fields=dict(entry_mode=entry_mode,dungeon=dungeon)
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
                         event_id=event.event_id,kind=event.kind,size=len(wire),**entry_fields)
                received=time.perf_counter()
                async with operation:
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
            self.log('connection_error',connection=index,error=type(error).__name__)
        except Exception as error:
            self.log('worker_error',connection=index,error=repr(error))
        finally:
            if native_sources is not None:native_sources.close()
            try:
                try:
                    if notifications:
                        notifications.cancel()
                        results=await asyncio.gather(notifications,return_exceptions=True)
                        if results and isinstance(results[0],Exception):
                            self.log('notification_error',connection=index,error=repr(results[0]))
                finally:
                    # Shutdown may cancel the socket task while its timer is
                    # draining. Still schedule the account's durable cleanup.
                    if business is not None:
                        self.local_sessions.discard(business)
                        await self.application.release(business)
            finally:
                # A save/release failure remains visible to the task observer,
                # but must never bypass transport closure.
                writer.close()
                try:await asyncio.wait_for(writer.wait_closed(),self.config.write_timeout)
                except (OSError,TimeoutError):pass
                self.log('connection_finished',connection=index)

    async def close(self):
        self.closing=True
        self.account_gateway.begin_close()
        if self.probe_transport:
            self.probe_transport.close();await self.probe_protocol.closed
        if self.listener:
            self.listener.close()
        tasks=list(self.connections)
        for writer in list(self.connections.values()):writer.close()
        if tasks:
            done,pending=await asyncio.wait(tasks,timeout=self.config.shutdown_timeout)
            for task in pending:task.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)
        # Python 3.13 Server.wait_closed can wait for active TLS transports.
        # Close peers first, otherwise idle clients can stall shutdown for minutes.
        if self.listener:
            try:await asyncio.wait_for(self.listener.wait_closed(),self.config.shutdown_timeout)
            except TimeoutError:self.log('listener_shutdown_timeout')
        await self.periodics.close()
        await self.account_gateway.close()
        await self.diagnostics.close()
        self.log('finished',**self.metrics,active=len(self.connections))
