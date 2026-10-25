"""Portable local launch, using only the share's independent development save."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from els_server.config import ServerConfig

FLAGS=['--until-stopped','--dungeon-probe','--npc-slot-test','--gate-test',
       '--population-test','--clear-test','--reward-test','--item-test',
       '--drop-probe','--drop-test','--boss-gauge-test','--shop-test',
       '--ice-test','--no-auto-entry','--lightweight-play','--local-resource-index']

def launch_plan(client):
    client=Path(client).resolve(strict=True)
    if client.name.casefold()!='x2_dx11.exe':raise ValueError('请选择 data/x2_dx11.exe。')
    from client_compatibility import check_client,ensure_unchanged
    from launch_friends_client import prepare_native_sources
    selection=check_client(client,ROOT)
    image=(Path(selection['native_directory'])/'native-prefixes.bin').read_bytes()
    sources=prepare_native_sources(image,client.parent,False,True)
    from local_stack_limits import source as stack
    from local_shortcut_totals import source as shortcut
    from artifact_restore_source import bridge_source as artifact
    from install_ed_shop_bridge import bridge_source as shop
    sources.update(stack_limits=stack(image),shortcut_totals=shortcut(image),artifact=artifact(image),shop=shop(image))
    ensure_unchanged(selection)
    config=ServerConfig.load(ROOT/'config/server.toml')
    if config.host!='127.0.0.1' or config.port!=19400 or config.mode!='local':
        raise ValueError('本地客户端接入要求独立回环服务端 127.0.0.1:19400。')
    if not config.state_file.is_relative_to(ROOT/'state'):
        raise ValueError('分享版存档必须位于解压目录的 state 内。')
    command=[sys.executable,'-B','-X','utf8',str(ROOT/'tools/probe_updated_client.py'),
             '--client',str(client),*FLAGS,'--server-config',str(ROOT/'config/server.toml'),
             '--state-file',str(config.state_file)]
    return dict(ok=True,client=str(client),state_file=str(config.state_file),command=command,
                prepared_script_sha256={k:hashlib.sha256(v.encode('utf8')).hexdigest() for k,v in sources.items()},
                starts_game=False,imports_owner_save=False),config

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--client',type=Path,default=os.environ.get('ELS_SHARE_CLIENT'))
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args(argv)
    if not args.client:parser.error('请从本地测试启动器选择自己的客户端，或传入 --client。')
    plan,config=launch_plan(args.client)
    if args.check:
        print(json.dumps(plan,ensure_ascii=True,indent=2));return 0
    # No seed database is read or copied. The existing server initializes its own new save.
    config.state_file.parent.mkdir(parents=True,exist_ok=True)
    return subprocess.call(plan['command'],cwd=ROOT)

if __name__=='__main__':raise SystemExit(main())
