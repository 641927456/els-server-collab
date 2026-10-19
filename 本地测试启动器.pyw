"""Share-only entry; the selected client is supplied by the native file picker."""
import argparse
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--client',type=Path,required=True)
args=parser.parse_args()
try:
    client=args.client.resolve(strict=True)
    if client.name.casefold()!='x2_dx11.exe':
        raise ValueError('请选择客户端 data 目录中的 x2_dx11.exe。')
    os.environ['ELS_SHARE_CLIENT']=str(client)
    # Do not inherit a user-root pointer from the owner's original launcher.
    os.environ['ELS_LOCAL_USER_ROOT']=str(ROOT)
    os.chdir(ROOT)
    sys.path.insert(0,str(ROOT))
    from launcher.__main__ import main
    sys.argv=[sys.argv[0],'--browser-app']
    raise SystemExit(main())
except Exception:
    import traceback
    report=ROOT/'state/launcher/startup-error.log'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(traceback.format_exc(),encoding='utf8')
    if os.name=='nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,'启动器未能打开，详情：\n'+str(report),'协作本地测试',16)
    raise
