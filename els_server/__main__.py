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
    manager=None
    if config.selected2026_pair_file is not None:
        from els_server.domain.selected_2026_pair_runtime import from_pack
        manager=from_pack(config.state_file,config.selected2026_pair_file)
    app=Application(config,activity2026_awards_factory=manager);server=GameServer(config,app,log)
    if manager is not None:manager.attach(app)
    stop=asyncio.Event();loop=asyncio.get_running_loop()
    previous={}
    for sig in (signal.SIGINT,signal.SIGTERM):
        previous[sig]=signal.signal(sig,lambda *_:loop.call_soon_threadsafe(stop.set))
    persistent=config.profile=='integrated_dx11'
    gm=None;console=None;endpoint=None;panel_nonce=None
    try:
        with SaveLease(config.state_file) if persistent else nullcontext():
            database_ready=False
            try:
                if persistent:
                    prepare_database(config.state_file);database_ready=True
                await app.start()
                if manager is not None:await app.call(manager.install)
                await server.start()
                automatic_panel=manager is not None and config.mode=='local' and gm_runtime_port is None
                if automatic_panel:
                    gm_runtime_port=0
                    gm_home=config.state_file.parent/'activity2026-gm'/config.state_file.stem
                if gm_runtime_port is not None:
                    import os,secrets
                    from els_server.gm_runtime import Runtime
                    from els_server.domain.gm_rates import configure
                    if config.mode!='friends' and manager is None:raise ValueError('Local GM requires the independent activity pack')
                    if config.mode=='friends':
                        configure(gm_home/'rates.json')
                        from els_server.domain.gm_events import configure as configure_events
                        configure_events(gm_home/'events.json')
                    gm=Runtime(app,server,gm_home/'audit.sqlite3')
                    token=secrets.token_urlsafe(48) if automatic_panel else os.environ.pop('ELS_GM_RUNTIME_TOKEN','')
                    await gm.start(gm_runtime_port,token)
                    if automatic_panel:
                        from els_server.selected2026_gm import Console
                        console=Console(0,gm.listener.sockets[0].getsockname()[1],token,gm_home)
                        console.start()
                        endpoint=gm_home/'endpoint.json';panel_nonce=secrets.token_hex(24)
                        info=dict(schema='selected2026-local-panel-v1',pid=os.getpid(),nonce=panel_nonce,
                            state_file=str(config.state_file.resolve()),url=f'http://127.0.0.1:{console.server.server_port}/')
                        if endpoint.exists():
                            prior=json.loads(endpoint.read_bytes())
                            if endpoint.is_symlink() or prior.get('schema')!=info['schema'] or prior.get('state_file')!=info['state_file']:
                                raise ValueError('Unrecognized local activity panel endpoint')
                        temporary=endpoint.with_suffix('.'+panel_nonce+'.tmp')
                        temporary.write_text(json.dumps(info)+'\n',encoding='utf8');temporary.replace(endpoint)
                        log('local_activity_panel_ready',url=info['url'],endpoint=str(endpoint))
                while not stop.is_set() and not (stop_file and stop_file.exists()):
                    if gm:await app.call(gm.tick)
                    try:await asyncio.wait_for(stop.wait(),.25)
                    except TimeoutError:pass
            finally:
                try:
                    if console:console.close()
                    if endpoint and endpoint.exists():
                        try:
                            info=json.loads(endpoint.read_bytes())
                            if info.get('nonce')==panel_nonce:endpoint.unlink()
                        except (OSError,ValueError):log('local_activity_panel_metadata_preserved')
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
        if config.selected2026_pair_file is not None:
            from els_server.domain.selected_2026_pair_runtime import from_pack
            from_pack(config.state_file,config.selected2026_pair_file)
        print(json.dumps(dict(asdict(config),client_data={'client_sha256':catalog.manifest['client_sha256'],'counts':dict(catalog.manifest['counts'],npc_definitions=catalog.npcs.manifest['count'])}),default=str,indent=2));return 0
    if args.gm_runtime_port is not None and (not 1024<=args.gm_runtime_port<=65535 or args.gm_home is None):parser.error('GM requires a valid runtime port and --gm-home')
    asyncio.run(serve(config,args.stop_file.resolve() if args.stop_file else None,args.gm_runtime_port,args.gm_home.resolve() if args.gm_home else None))
    return 0

if __name__=='__main__':raise SystemExit(main())
