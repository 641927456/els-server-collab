"""Open the local activity panel after the single-player server has started."""
import argparse,json,sys,urllib.request,webbrowser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def panel(config_path,check=False):
    from els_server.config import ServerConfig
    cfg=ServerConfig.load(config_path)
    if cfg.mode!='local' or cfg.selected2026_pair_file is None:
        raise ValueError('当前单机版本尚未安装活动管理包')
    if check:return dict(ok=True,loopback_only=True,manual_browser_only=True)
    home=cfg.state_file.parent/'activity2026-gm'/cfg.state_file.stem
    info=json.loads((home/'endpoint.json').read_bytes())
    from urllib.parse import urlsplit
    url=info['url'];parsed=urlsplit(url)
    if (info.get('schema')!='selected2026-local-panel-v1' or info.get('state_file')!=str(cfg.state_file.resolve())
        or parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or parsed.path!='/'
        or parsed.username or parsed.password or parsed.query or parsed.fragment):raise ValueError('本地活动管理地址不匹配')
    key=(home/'selected2026-access.key').read_text('ascii').strip()
    request=urllib.request.Request(url+'api/selected2026',headers={'X-GM-Key':key})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as reply:
        status=json.loads(reply.read())
    if status.get('ok') is not True:raise ValueError('本地活动管理服务尚未就绪')
    return url+'#key='+key

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'config/server.toml');p.add_argument('--check',action='store_true');args=p.parse_args()
    try:
        result=panel(args.config,args.check)
        if args.check:print(json.dumps(result));return 0
        webbrowser.open(result,new=2);print('已打开本地活动管理');return 0
    except (OSError,ValueError,KeyError) as error:
        print('请先启动单机服务，再打开本地活动GM。'+str(error));return 1

if __name__=='__main__':raise SystemExit(main())
