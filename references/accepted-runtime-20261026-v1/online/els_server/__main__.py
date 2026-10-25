"""python -m els_server --config config/server.toml"""
import argparse
import asyncio
from contextlib import nullcontext
from dataclasses import asdict,replace
import json
from pathlib import Path
import signal
from els_server.config import ServerConfig
from els_server.application import Application
from els_server.observability import EventLog
from els_server.storage.lifecycle import SaveLease,prepare_database,checkpoint_database
from els_server.transport import GameServer


async def serve(config,stop_file=None,gm_runtime_port=None,gm_home=None):
    log=EventLog(config)
    app=Application(config);server=GameServer(config,app,log)
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    previous={}
    for sig in (signal.SIGINT,signal.SIGTERM):
        previous[sig]=signal.signal(sig,lambda *_:loop.call_soon_threadsafe(stop.set))
    persistent=config.profile=='integrated_dx11'
    gm=None
    try:
        with SaveLease(config.state_file) if persistent else nullcontext():
            database_ready=False
            try:
                if persistent:
                    prepare_database(config.state_file);database_ready=True
                await app.start();await server.start()
                if gm_runtime_port is not None:
                    import os
                    from els_server.gm_runtime import Runtime
                    from els_server.domain.gm_rates import configure
                    if config.mode!='friends':raise ValueError('Online GM runtime requires friends mode')
                    configure(gm_home/'rates.json')
                    from els_server.domain.gm_events import configure as configure_events
                    configure_events(gm_home/'events.json')
                    gm=Runtime(app,server,gm_home/'audit.sqlite3')
                    await gm.start(gm_runtime_port,os.environ.pop('ELS_GM_RUNTIME_TOKEN',''))
                while not stop.is_set() and not (stop_file and stop_file.exists()):
                    if gm:await app.call(gm.tick)
                    try:await asyncio.wait_for(stop.wait(),.25)
                    except TimeoutError:pass
            finally:
                if gm:await gm.close()
                await server.close()
                app.close()
                if database_ready:
                    log('database_checkpoint',result=checkpoint_database(config.state_file))
    except Exception as error:
        log('server_failed',error=repr(error));raise
    finally:
        app.close()
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
    asyncio.run(serve(config,args.stop_file.resolve() if args.stop_file else None,args.gm_runtime_port,args.gm_home.resolve() if args.gm_home else None))
    return 0

if __name__=='__main__':raise SystemExit(main())
