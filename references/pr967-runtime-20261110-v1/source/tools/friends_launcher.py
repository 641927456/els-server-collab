"""Portable entry point; ask the user to select their existing, unmodified EXE."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--client',type=Path);p.add_argument('--check',action='store_true')
    a=p.parse_args();config=ROOT/'state/friends-client.json';saved=ROOT/'state/client-path.txt'
    if not config.exists():
        print('请将你自己的连接配置复制到 state/friends-client.json，再启动登录器。每位朋友使用各自的配置。')
        return 2
    client=a.client
    if client is None and saved.exists():client=Path(saved.read_text(encoding='utf8').strip())
    if client is None or not client.is_file():
        if a.check:raise ValueError('Check requires --client or a saved client path')
        result=subprocess.run(['powershell.exe','-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/select_friends_client.ps1')],capture_output=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or not result.stdout.strip():return 1
        client=Path(result.stdout.strip())
    from tools.launch_friends_client import main as launch
    args=['--config',str(config),'--client',str(client)]+(['--check'] if a.check else [])
    # Save only the selected path, never client files, credentials or saves.
    if not a.check:saved.write_text(str(client),encoding='utf8')
    return launch(args)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as error:
        print('启动失败：'+str(error));raise SystemExit(1)
