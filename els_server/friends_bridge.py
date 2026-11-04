"""Loopback-only adapter: native TCP + UDP discovery over an authenticated TLS tunnel."""
from dataclasses import dataclass
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import re
import ssl
import socket
import time
from els_server.friends_wire import read_json,write_json
from els_server.friends_bootstrap import RelayBootstrapProbe

RESERVED_NATIVE_TTL=120.0


@dataclass(frozen=True)
class BridgeConfig:
    host: str
    port: int
    name: str
    token: str
    certificate_sha256: str
    local_port: int = 19400
    probe_port: int = 19401

    def __post_init__(self):
        if not isinstance(self.host,str) or not self.host or any(c in self.host for c in '/\\\r\n '):raise ValueError('Invalid remote host')
        for port in (self.port,self.local_port,self.probe_port):
            if type(port) is not int or not 1<=port<=65535:raise ValueError('Invalid bridge port')
        if not isinstance(self.name,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,23}',self.name):raise ValueError('Invalid account name')
        if not isinstance(self.token,str) or not 32<=len(self.token)<=128:raise ValueError('Invalid account token')
        if not isinstance(self.certificate_sha256,str) or not re.fullmatch('[a-f0-9]{64}',self.certificate_sha256):raise ValueError('Expected pinned certificate SHA256')

    @classmethod
    def load(cls,path):return cls(**json.loads(Path(path).read_text(encoding='utf8')))


class Bridge:
    def __init__(self,config,log=lambda *a,**kw:None):
        self.config=config;self.log=log;self.listener=None;self.udp=None;self.probe=None
        self.account_ids=set();self.tasks=set();self.closing=False
        self.game_address=None;self.relay_supported=False;self.relay=None;self.relay_task=None
        self.relay_control_version=0;self.relay_control_active=False
        self.reserved_native=None;self.reserved_expiry=None
        from els_server.domain.pvp_support import EMPTY
        self.pvp_support_version=0;self.pvp_support=dict(EMPTY)

    async def _close_writer(self,writer):
        writer.close()
        try:await asyncio.wait_for(writer.wait_closed(),5)
        except BaseException:
            # A failed TLS shutdown must release this owned transport too.
            writer.transport.abort()
            raise

    async def remote(self,role=None):
        # Trust is an explicit certificate pin, verified BEFORE any token is sent.
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        writer=None;stage='connect_tls';started=time.monotonic()
        try:
            async with asyncio.timeout(10):
                reader,writer=await asyncio.open_connection(self.config.host,self.config.port,ssl=context,server_hostname=self.config.host)
                connected=time.monotonic()
                if role=='relay':
                    sock=writer.get_extra_info('socket')
                    if sock is not None:
                        try:
                            sock.setsockopt(socket.SOL_SOCKET,socket.SO_KEEPALIVE,1)
                            for option,value in (('TCP_KEEPIDLE',30),('TCP_KEEPINTVL',10),('TCP_KEEPCNT',3)):
                                if hasattr(socket,option):sock.setsockopt(socket.IPPROTO_TCP,getattr(socket,option),value)
                        except OSError as error:self.log('relay_keepalive_unavailable',reason=type(error).__name__)
                stage='certificate_pin'
                certificate=writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
                if not hmac.compare_digest(hashlib.sha256(certificate).hexdigest(),self.config.certificate_sha256):raise ValueError('Server certificate fingerprint mismatch')
                auth=dict(name=self.config.name,token=self.config.token)
                if role is not None:auth['role']=role
                control=role=='relay' and self.relay_control_version==1
                if control:auth['relay_control_version']=1
                stage='authentication_write'
                await write_json(writer,auth)
                stage='authentication_reply'
                reply=await read_json(reader)
                if reply.get('ok') is not True:raise ValueError('Account authentication failed')
                identity=reply.get('account_id')
                if type(identity) is not int or not 2<=identity<2**63 or reply.get('probe_port')!=self.config.probe_port:raise ValueError('Server/client bridge settings differ')
                self.account_ids.add(identity)
                if role is None:self.relay_supported=reply.get('relay_version')==1
                version=reply.get('relay_control_version',0)
                if type(version) is not int or version not in (0,1):raise ValueError('Server relay control version differs')
                self.relay_control_version=version
                support_version=reply.get('pvp_support_version',0)
                if type(support_version)is not int or support_version not in(0,1):raise ValueError('PvP support control version differs')
                self.pvp_support_version=support_version
                if role=='relay':self.relay_control_active=control and self.relay_control_version==1
                self.log('bridge_remote_ready',role=role or 'native',connect_tls_ms=round((connected-started)*1000),authentication_ms=round((time.monotonic()-connected)*1000))
                return reader,writer
        except BaseException as error:
            self.log('bridge_remote_failed',stage=stage,role=role or 'native',reason=type(error).__name__,elapsed_ms=round((time.monotonic()-started)*1000))
            if writer:
                try:await self._close_writer(writer)
                except (ConnectionError,OSError,TimeoutError):pass
            raise

    async def start(self):
        try:await self._start()
        except BaseException:
            try:await self.close()
            except (ConnectionError,OSError,TimeoutError) as error:
                self.log('bridge_cleanup_failed',reason=type(error).__name__)
            raise

    async def _start(self):
        reader,writer=await self.remote()
        # Keep the verified preflight stream for exactly one native connection.
        # Its original welcome stays unread and is forwarded byte-for-byte.
        self.reserved_native=(reader,writer,time.monotonic())
        async def expire_reserved():
            await asyncio.sleep(RESERVED_NATIVE_TTL)
            await self._release_reserved()
        self.reserved_expiry=asyncio.create_task(expire_reserved())
        def discovery(address):self.game_address=address
        self.udp,self.probe=await asyncio.get_running_loop().create_datagram_endpoint(
            lambda:RelayBootstrapProbe(self,discovery),local_addr=('127.0.0.1',self.config.probe_port))
        try:self.listener=await asyncio.start_server(self.accept,'127.0.0.1',self.config.local_port,limit=65536)
        except BaseException:self.udp.close();await self.probe.closed;raise
        if self.relay_supported:
            from els_server.friends_relay import RelayClient,RelayBusyError
            for attempt in range(6):
                self.relay=RelayClient(self,reconnect=True);self.relay_task=asyncio.create_task(self.relay.run())
                ready=asyncio.create_task(self.relay.ready.wait())
                try:
                    done,_=await asyncio.wait((ready,self.relay_task),timeout=10,return_when=asyncio.FIRST_COMPLETED)
                    if self.relay_task in done:self.relay_task.result();raise ValueError('Combat relay stopped during startup')
                    if ready not in done:raise TimeoutError('Combat relay startup')
                    break
                except RelayBusyError:
                    # Allow an exiting relay's serialized cleanup to finish;
                    # never replace or disconnect a live endpoint.
                    if attempt==5:raise
                    await asyncio.sleep(.2)
                finally:
                    ready.cancel();await asyncio.gather(ready,return_exceptions=True)

    def accept(self,reader,writer):
        if self.closing or len(self.tasks)>=8:writer.close();return
        task=asyncio.create_task(self.handle(reader,writer));self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def support_status(self,value):
        from els_server.domain.pvp_support import decode
        value=decode(value)
        if value==self.pvp_support:return
        self.pvp_support=value
        if self.pvp_support_version==1 and self.relay_control_active and self.relay is not None:
            self.relay.outgoing.put(b'\7'+json.dumps(value,separators=(',',':')).encode())

    async def _release_reserved(self):
        reserved=self.reserved_native;self.reserved_native=None
        if reserved is None:return
        try:await self._close_writer(reserved[1])
        except (ConnectionError,OSError,TimeoutError):pass

    async def native_remote(self):
        reserved=self.reserved_native;self.reserved_native=None
        if self.reserved_expiry:
            self.reserved_expiry.cancel()
            await asyncio.gather(self.reserved_expiry,return_exceptions=True)
            self.reserved_expiry=None
        if reserved is not None:
            reader,writer,created=reserved
            if (time.monotonic()-created<RESERVED_NATIVE_TTL
                    and not reader.at_eof() and not writer.is_closing()):
                self.log('bridge_native_preflight_reused')
                return reader,writer
            try:await self._close_writer(writer)
            except (ConnectionError,OSError,TimeoutError):pass
        # Only authentication is repeated. No native welcome or game bytes have
        # been forwarded here, so a purchase/save/selection can never be replayed.
        deadline=time.monotonic()+10
        for attempt in range(2):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Native connection budget')
            try:
                async with asyncio.timeout(remaining):return await self.remote()
            except (ConnectionError,OSError,TimeoutError,asyncio.IncompleteReadError):
                if attempt or deadline-time.monotonic()<.2:raise
                self.log('bridge_native_connect_retry',attempt=2)
                await asyncio.sleep(.15)

    async def handle(self,reader,writer):
        remote_writer=None;pumps=[]
        async def copy(source,destination):
            while True:
                data=await source.read(65536)
                if not data:return
                destination.write(data)
                await asyncio.wait_for(destination.drain(),15)
        try:
            remote_reader,remote_writer=await self.native_remote()
            pumps=[asyncio.create_task(copy(reader,remote_writer)),asyncio.create_task(copy(remote_reader,writer))]
            done,_=await asyncio.wait(pumps,return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
        except (ValueError,ConnectionError,OSError,TimeoutError,asyncio.IncompleteReadError) as error:
            # Tokens, documents and packet bodies are never included in logs.
            self.log('bridge_connection_failed',reason=type(error).__name__)
        finally:
            for task in pumps:task.cancel()
            if pumps:await asyncio.gather(*pumps,return_exceptions=True)
            for stream in (remote_writer,writer):
                if stream:
                    try:await self._close_writer(stream)
                    except (ConnectionError,OSError,TimeoutError):pass

    async def close(self):
        self.closing=True
        if self.listener:self.listener.close()
        tasks=list(self.tasks)
        if self.reserved_expiry:tasks.append(self.reserved_expiry)
        if self.relay_task:tasks.append(self.relay_task)
        for task in tasks:task.cancel()
        try:
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
        finally:
            await self._release_reserved()
            if self.udp:self.udp.close();await self.probe.closed
            # Python 3.13 waits for accepted streams; cancel their owners first.
            if self.listener:await asyncio.wait_for(self.listener.wait_closed(),5)


def _owned_validate_owner(pid,created):
    if pid is None and created is None:return
    if type(pid) is not int or pid<=0:raise ValueError('Expected paired positive owner PID and creation time')
    if type(created) not in (int,float) or not 0<created<float('inf'):
        raise ValueError('Expected paired positive owner PID and finite creation time')


def owner_alive(pid,created):
    import sys
    libraries=str(Path(__file__).resolve().parents[1]/'tools/pylibs')
    if libraries not in sys.path:sys.path.insert(0,libraries)
    import psutil
    try:
        process=psutil.Process(pid)
        return process.is_running() and process.create_time()==created
    except psutil.NoSuchProcess:return False
    except psutil.AccessDenied:return True


def bridge_failure_message(error):
    from els_server.friends_relay import RelayBusyError
    if isinstance(error,RelayBusyError):
        return '账号的上一次联机连接尚未释放。请正常退出其他连接后重试；支持心跳的连接会在失联约30秒后释放。'
    if isinstance(error,asyncio.IncompleteReadError):
        return '联机中继连接已结束，桥接未能维持。请正常退出游戏后重试，并保留本次诊断日志。'
    if isinstance(error,TimeoutError):
        return '联机中继响应超时，连接已安全释放。请检查网络后重试。'
    return '联机桥接连接已中断，请检查网络并保留本次诊断日志。'


async def main(config_path,stop_file=None,owner_pid=None,owner_created=None):
    _owned_validate_owner(owner_pid,owner_created)
    bridge=Bridge(BridgeConfig.load(config_path),lambda event,**kw:print(json.dumps(dict(event=event,**kw)),flush=True))
    try:
        if owner_pid is not None and not owner_alive(owner_pid,owner_created):
            bridge.log('bridge_owner_exited');return
        await bridge.start()
        print('ELS_BRIDGE_READY',flush=True)
        while not (stop_file and Path(stop_file).exists()):
            if owner_pid is not None and not owner_alive(owner_pid,owner_created):
                bridge.log('bridge_owner_exited');break
            if bridge.relay_task and bridge.relay_task.done():
                bridge.relay_task.result()
                raise ValueError('Combat relay stopped')
            from els_server.domain.pvp_support import read_owned
            bridge.support_status(read_owned(Path(stop_file).with_name('pvp-hp-status.json')if stop_file else None,owner_pid))
            await asyncio.sleep(.25)
    finally:await bridge.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--owner-pid',type=int)
    parser.add_argument('--owner-created',type=float)
    args=parser.parse_args()
    try:_owned_validate_owner(args.owner_pid,args.owner_created)
    except ValueError as error:parser.error(str(error))
    from els_server.friends_relay import RelayBusyError
    try:asyncio.run(main(args.config,args.stop_file,args.owner_pid,args.owner_created))
    except (RelayBusyError,asyncio.IncompleteReadError,ConnectionError,OSError,TimeoutError) as error:
        print(json.dumps(dict(event='bridge_runtime_failed',reason=type(error).__name__)),flush=True)
        print('ELS_LAUNCH_ERROR: '+bridge_failure_message(error),flush=True)
        raise SystemExit(2)
