"""python -m els_server --config config/server.toml"""
import argparse
import asyncio
from contextlib import nullcontext,contextmanager
from dataclasses import asdict,replace
import json
from pathlib import Path
import signal
import gc
import sys
from els_server.config import ServerConfig
from els_server.application import Application
from els_server.observability import EventLog
from els_server.storage.lifecycle import SaveLease,prepare_database,checkpoint_database
from els_server.transport import GameServer


@contextmanager
def _native_timing():
    if sys.platform!='win32':
        yield
        return
    import ctypes
    timer=ctypes.WinDLL('winmm.dll')
    for name in ('timeBeginPeriod','timeEndPeriod'):
        function=getattr(timer,name);function.argtypes=[ctypes.c_uint];function.restype=ctypes.c_uint
    if timer.timeBeginPeriod(1)!=0:raise OSError('Unable to request native1ms timer resolution')
    try:yield
    finally:
        if timer.timeEndPeriod(1)!=0:raise OSError('Unable to release native1ms timer resolution')


def _normal_scheduling():
    if sys.platform!='win32':return None
    import psutil
    process=psutil.Process()
    process.nice(psutil.NORMAL_PRIORITY_CLASS)
    process.ionice(psutil.IOPRIO_NORMAL)
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    for name in('SetProcessInformation','GetProcessInformation'):
        function=getattr(kernel,name)
        function.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong]
        function.restype=ctypes.c_int
    handle=kernel.GetCurrentProcess();memory=ctypes.c_ulong(5)
    # CPU and I/O normalization do not restore an inherited low memory
    # priority. Select the normal default before warming assets or workers.
    if not kernel.SetProcessInformation(handle,0,ctypes.byref(memory),ctypes.sizeof(memory)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.GetProcessInformation(handle,0,ctypes.byref(memory),ctypes.sizeof(memory)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.GetCurrentThread.restype=ctypes.c_void_p
    kernel.SetThreadPriority.argtypes=[ctypes.c_void_p,ctypes.c_int]
    kernel.SetThreadPriority.restype=ctypes.c_int
    kernel.GetThreadPriority.argtypes=[ctypes.c_void_p]
    kernel.GetThreadPriority.restype=ctypes.c_int
    thread=kernel.GetCurrentThread()
    if not kernel.SetThreadPriority(thread,1):raise ctypes.WinError(ctypes.get_last_error())
    if kernel.GetThreadPriority(thread)!=1:raise OSError('Unable to select network thread scheduling')
    current=dict(priority_class=int(process.nice()),IO_priority=int(process.ionice()),memory_priority=memory.value,network_thread_priority=kernel.GetThreadPriority(thread))
    if current!=dict(priority_class=32,IO_priority=2,memory_priority=5,network_thread_priority=1):raise OSError('Unable to select normal server scheduling')
    return current


async def serve(config,stop_file=None,gm_runtime_port=None,gm_home=None,*,freeze_static=False):
    scheduling=_normal_scheduling()
    log=EventLog(config)
    if scheduling is not None:log('server_scheduling',**scheduling)
    app=Application(config);server=GameServer(config,app,log)
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    previous={}
    for sig in (signal.SIGINT,signal.SIGTERM):
        previous[sig]=signal.signal(sig,lambda *_:loop.call_soon_threadsafe(stop.set))
    persistent=config.profile=='integrated_dx11'
    gm=None;frozen=False
    try:
        with SaveLease(config.state_file) if persistent else nullcontext():
            database_ready=False
            try:
                if persistent:
                    prepare_database(config.state_file);database_ready=True
                settings_home=gm_home or config.state_file.parent/'gm'
                from els_server.domain.gm_rates import configure
                from els_server.domain.gm_events import configure as configure_events
                configure(settings_home/'rates.json');configure_events(settings_home/'events.json')
                await app.start()
                if freeze_static:
                    # The standalone process has no players yet. Keep its
                    # prepared catalog heap out of subsequent cyclic scans.
                    gc.collect();gc.freeze();frozen=True
                    log('static_heap_prepared',frozen_objects=gc.get_freeze_count())
                await server.start()
                if gm_runtime_port is not None:
                    import os
                    from els_server.gm_runtime import Runtime
                    if config.mode!='friends':raise ValueError('Online GM runtime requires friends mode')
                    gm=Runtime(app,server,gm_home/'audit.sqlite3')
                    await gm.start(gm_runtime_port,os.environ.pop('ELS_GM_RUNTIME_TOKEN',''))
                while not stop.is_set() and not (stop_file and stop_file.exists()):
                    if gm:await app.call(gm.tick)
                    try:await asyncio.wait_for(stop.wait(),.25)
                    except TimeoutError:pass
            finally:
                from els_server.cleanup import cleanup_all_async
                await cleanup_all_async(lambda:gm.close() if gm else None,
                    server.close,app.close)
                if database_ready:
                    log('database_checkpoint',result=checkpoint_database(config.state_file))
    except Exception as error:
        log('server_failed',error=repr(error));raise
    finally:
        try:app.close()
        finally:
            if frozen:gc.unfreeze()
        for sig,handler in previous.items():signal.signal(sig,handler)
        log.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'config/server.toml')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--log-dir',type=Path)
    parser.add_argument('--gm-runtime-port',type=int)
    parser.add_argument('--gm-home',type=Path)
    args=parser.parse_args(argv)
    config=ServerConfig.load(args.config)
    if args.log_dir:config=replace(config,log_dir=args.log_dir.resolve())
    if args.check:
        from els_server.game_data import client_data
        catalog=client_data()
        print(json.dumps(dict(asdict(config),client_data={'client_sha256':catalog.manifest['client_sha256'],'counts':dict(catalog.manifest['counts'],npc_definitions=catalog.npcs.manifest['count'])}),default=str,indent=2));return 0
    if args.gm_runtime_port is not None and (not 1024<=args.gm_runtime_port<=65535 or args.gm_home is None):parser.error('GM requires a valid runtime port and --gm-home')
    with _native_timing():
        asyncio.run(serve(config,args.stop_file.resolve() if args.stop_file else None,args.gm_runtime_port,args.gm_home.resolve() if args.gm_home else None,freeze_static=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
