"""Start the pinned native client against a separately running friends server."""
import argparse
import datetime
import os
import hashlib
from pathlib import Path
import subprocess
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.friends_bridge import BridgeConfig


class ClientLaunchError(ValueError):
    pass


def bridge_failure_message(path,started=False):
    # The paired bridge writes fixed human-readable errors without credentials.
    with Path(path).open('rb') as stream:
        stream.seek(0,2);stream.seek(max(0,stream.tell()-32768))
        lines=stream.read().decode('utf8',errors='replace').splitlines()
    for line in reversed(lines):
        if line.startswith('ELS_LAUNCH_ERROR: '):return line[len('ELS_LAUNCH_ERROR: '):][:1000]
    return ('联机连接已中断，请正常退出游戏后重试，并保留诊断日志。' if started else
            '联机桥接未能建立，请查看诊断日志后重试。')


def verify_client(client, allow_variants=False):
    if not client.is_file():
        raise ClientLaunchError('找不到游戏程序，请选择包含 x2_dx11.exe 的客户端目录。')
    if allow_variants:
        # A file hash is not a compatibility test. Accept other x64 builds;
        # the live adapter still verifies native entry points before use.
        with client.open('rb') as stream:
            header=stream.read(64)
            if len(header)!=64 or header[:2]!=b'MZ':
                raise ClientLaunchError('所选游戏程序不是有效的 Windows 客户端。')
            offset=struct.unpack_from('<I',header,60)[0]
            if offset>client.stat().st_size-6:
                raise ClientLaunchError('游戏程序文件不完整，请重新复制客户端。')
            stream.seek(offset)
            if stream.read(6)!=b'PE\0\0\x64\x86':
                raise ClientLaunchError('请选择 64 位的 x2_dx11.exe 客户端。')
        return
    from els_server.game_data import CLIENT_SHA
    with client.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=CLIENT_SHA:
            raise ClientLaunchError('客户端版本与严格配置不同；请使用朋友服兼容版启动器。')


def prepare_native_sources(image, directory, allow_variants=False, resource_index=True):
    from local_startup_config_fix import startup_config_source
    from dx11_resource_compat import resource_compat_source,pinned_client_profile
    from local_resource_index_compat import source as index_source
    prepared={'config':startup_config_source(image)}
    if pinned_client_profile(directory):
        # This profile is part of the signed runtime, not a temporary local entry.
        # A changed resource fails before launch; never silently drop its repair.
        prepared['digest']=resource_compat_source(image,directory,use_pinned_profile=True)
        if resource_index:
            prepared['index']=index_source(image,directory,use_retained_original_indexes=True)
        print('CLIENT_RESOURCE_PROFILE: verified fixed client/resources; native digest and disk-index checks retained.',flush=True)
        return prepared
    for name,builder in [('digest',resource_compat_source)]+([('index',index_source)] if resource_index else []):
        try:
            if name=='index':
                source=builder(image,directory,allow_variants=allow_variants)
                if source is not None:prepared[name]=source
            else:prepared[name]=builder(image,directory)
        except FileNotFoundError as error:
            raise ClientLaunchError('客户端缺少文件：'+Path(error.filename).name+'。请补齐客户端。') from error
        except ValueError as error:
            archive_mismatch=('differs from the witnessed archive' in str(error) or
                              str(error).startswith('Unverified local archive:'))
            if not allow_variants or not archive_mismatch:
                raise
            # Only witnessed archives receive the local mixed-resource repair.
            # Other archives keep the game's original parsing/integrity path.
            print('CLIENT_COMPAT_NOTICE: '+name+' uses the original client resource path.',flush=True)
    return prepared


def compatibility_preflight(client,allow_variants=False):
    verify_client(client,allow_variants)
    from client_compatibility import check_client
    try:return check_client(client,ROOT,emit=lambda line:print(line,flush=True))
    except ValueError as error:raise ClientLaunchError(str(error)) from error


def _wait_owned_game_probe(game,bridge,stop,bridge_log):
    while game.poll() is None:
        bridge_exit=bridge.poll()
        if bridge_exit is not None:
            # The owned probe signals this marker BEFORE detaching and hashing
            # its final report. A normal bridge exit can precede that cleanup.
            # Preserve the probe's actual exit code and bound the cleanup wait.
            if bridge_exit==0 and stop.is_file():
                try:return game.wait(timeout=15)
                except subprocess.TimeoutExpired as error:
                    raise ClientLaunchError('游戏退出收尾超时，请保留本次诊断日志后重试。') from error
            raise ClientLaunchError(bridge_failure_message(bridge_log,started=True))
        time.sleep(.5)
    return game.returncode


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--client',type=Path,default=Path('D:/艾尔之光/data/x2_dx11.exe'))
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--allow-client-variants',action='store_true',help='Friends-only: allow different EXE/KOM hashes; native interface checks remain enabled')
    args=parser.parse_args(argv)
    config=BridgeConfig.load(args.config)
    if config.local_port!=19400:parser.error('Pinned native adapter requires local TCP 19400')
    selection=compatibility_preflight(args.client,args.allow_client_variants)
    flags=['--until-stopped','--dungeon-probe','--npc-slot-test','--gate-test',
           '--population-test','--clear-test','--reward-test','--item-test',
           '--drop-probe','--drop-test','--boss-gauge-test','--shop-test','--ice-test',
           '--no-auto-entry','--lightweight-play','--local-resource-index','--remote-bridge']
    command=[sys.executable,str(ROOT/'tools/probe_updated_client.py'),'--client',str(args.client.resolve()),*flags]
    if args.allow_client_variants:command.append('--allow-client-variants')
    if args.check:
        sys.path.insert(0,str(ROOT/'tools'))
        image=(Path(selection['native_directory'])/'x2-runtime.bin').read_bytes()
        prepare_native_sources(image,args.client.parent,args.allow_client_variants)
        from install_ed_shop_bridge import bridge_source
        bridge_source(image)
        from client_compatibility import ensure_unchanged
        try:ensure_unchanged(selection)
        except ValueError as error:raise ClientLaunchError(str(error)) from error
        print('Client preflight ready. Full-file version lock: '+('off' if args.allow_client_variants else 'on')+'. Native interface checks remain enabled.')
        return 0
    sys.path.insert(0,str(ROOT/'tools/pylibs'))
    import psutil
    if any((q.info['name'] or '').lower() in ('x2.exe','x2_dx11.exe') for q in psutil.process_iter(['name'])):
        raise ClientLaunchError('检测到已有游戏运行，请正常退出该游戏后再启动朋友服。')
    from client_compatibility import ensure_unchanged
    try:ensure_unchanged(selection)
    except ValueError as error:raise ClientLaunchError(str(error)) from error
    owner_pid=os.getpid()
    owner_created=psutil.Process(owner_pid).create_time()
    folder=ROOT/'state/friends-client'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder.mkdir(parents=True);stop=folder/'bridge.stop'
    command+=['--remote-stop-file',str(stop)]
    with (folder/'bridge.log').open('w',encoding='utf8') as log:
        bridge=subprocess.Popen([sys.executable,'-X','utf8','-m','els_server.friends_bridge','--config',str(args.config.resolve()),'--stop-file',str(stop),'--owner-pid',str(owner_pid),'--owner-created',repr(owner_created)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        game=None
        try:
            deadline=time.monotonic()+20
            while bridge.poll() is None and time.monotonic()<deadline:
                if 'ELS_BRIDGE_READY' in (folder/'bridge.log').read_text(encoding='utf8'):break
                time.sleep(.1)
            else:raise ClientLaunchError(bridge_failure_message(folder/'bridge.log'))
            game=subprocess.Popen(command,cwd=ROOT)
            return _wait_owned_game_probe(game,bridge,stop,folder/'bridge.log')
        finally:
            try:stop.write_text('owned client ended',encoding='utf8')
            except OSError as error:print('ELS_BRIDGE_STOP_WARNING: '+type(error).__name__,flush=True)
            try:bridge.wait(timeout=15)
            except subprocess.TimeoutExpired:bridge.terminate();bridge.wait(timeout=5)


if __name__=='__main__':
    try:raise SystemExit(main())
    except ClientLaunchError as error:
        print('ELS_LAUNCH_ERROR: '+str(error),flush=True)
        raise SystemExit(2)
