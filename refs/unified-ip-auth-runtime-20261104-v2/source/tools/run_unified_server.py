"""Own a standard authenticated server for the lifetime of its launcher."""
import argparse, asyncio, json, sys
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/pylibs'))
import psutil
from els_server.config import ServerConfig
from els_server.__main__ import serve

async def run(args):
    owner=psutil.Process(args.owner_pid)
    expected=int((owner.create_time()+11644473600)*10000000)
    if abs(expected-args.owner_created)>10000:raise ValueError('Launcher identity changed')
    config=replace(ServerConfig.load(args.config),log_dir=args.ready.parent/'runs'/args.ready.stem)
    args.ready.parent.mkdir(parents=True,exist_ok=True)
    # The process and config are owned; an occupied listener is a hard failure.
    server=asyncio.create_task(serve(config,args.stop_file,gm_home=args.config.parent/'gm'))
    try:
        while not server.done():
            if not owner.is_running() or owner.status()==psutil.STATUS_ZOMBIE:
                args.stop_file.write_text('launcher exited','utf8');break
            if not args.ready.exists():
                for log in config.log_dir.glob('*'):
                    if not log.is_file():continue
                    rows=log.read_text('utf8',errors='replace').splitlines()
                    if any(json.loads(row).get('event')=='listening' for row in rows if row.startswith('{')):
                        args.ready.write_text(json.dumps(dict(pid=__import__('os').getpid(),host=config.host,port=config.port)),'utf8')
            await asyncio.sleep(.25)
        await server
    finally:
        args.stop_file.write_text('owned server closing','utf8')
        if not server.done():await server
        args.ready.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','ready','stop-file'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--owner-pid',type=int,required=True);p.add_argument('--owner-created',type=int,required=True)
    asyncio.run(run(p.parse_args()))
