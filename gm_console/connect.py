"""Open a remote GM console through OpenSSH; no keys written to disk/logs.

Run on the administrator's PC: python -m gm_console.connect Administrator@HOST
Uses the user's existing SSH identity/agent and normal host-key checking.
"""
import argparse
from pathlib import Path
import re
import queue
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser


def read_key(child,timeout):
    result=queue.Queue(maxsize=1)
    def read():
        try:result.put(child.stdout.readline(130).strip())
        except Exception:result.put('')
    threading.Thread(target=read,daemon=True).start()
    try:key=result.get(timeout=timeout)
    except queue.Empty:raise ValueError('SSH 连接或读取管理密钥超时，请检查登录身份及服务状态') from None
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,128}',key):
        raise ValueError('未取得有效管理访问密钥，请确认 GM 已部署及 SSH 登录权限')
    return key


def close_ssh(child):
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
    if child.stdout:child.stdout.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('destination',help='Windows SSH 登录，如 Administrator@134.175.57.52')
    p.add_argument('--port','--local-port',dest='local_port',type=int,default=18765)
    p.add_argument('--remote-port',type=int,default=18765)
    p.add_argument('--ssh-port',type=int,default=22)
    p.add_argument('--identity',type=Path)
    p.add_argument('--ssh-config',type=Path)
    p.add_argument('--known-hosts',type=Path,help='使用既有固定主机指纹文件，不创建或接受新指纹')
    p.add_argument('--timeout',type=int,default=45,help='取得密钥的总时限，5–120秒')
    a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*',a.destination):p.error('SSH 目标格式无效')
    if not all(1024<=v<=65535 for v in (a.local_port,a.remote_port)) or not 1<=a.ssh_port<=65535:p.error('端口无效')
    if not 5<=a.timeout<=120:p.error('连接时限无效')
    for path in (a.identity,a.ssh_config,a.known_hosts):
        if path is not None and not path.resolve().is_file():p.error('指定 SSH 身份或配置文件不存在')
    ssh=shutil.which('ssh')
    if ssh is None:raise SystemExit('请先安装 Windows OpenSSH 客户端。')
    with socket.socket() as test:
        try:test.bind(('127.0.0.1',a.local_port))
        except OSError:raise SystemExit('本地 GM 端口已占用，请先关闭之前的连接窗口。')
    # Constant, read-only remote command. The access key stays in a pipe and
    # the temporary URL fragment; app.js immediately removes the fragment.
    command="powershell.exe -NoProfile -NonInteractive -Command \"$ErrorActionPreference='Stop';Get-Content -LiteralPath 'C:\\ElsFriends\\state\\gm\\access.key';while($true){Start-Sleep -Seconds 3600}\""
    args=[ssh,'-T','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1',
        '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
        '-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3','-p',str(a.ssh_port)]
    if a.identity is not None:args+=['-i',str(a.identity.resolve())]
    if a.ssh_config is not None:args+=['-F',str(a.ssh_config.resolve())]
    if a.known_hosts is not None:args+=['-o',f'UserKnownHostsFile={a.known_hosts.resolve()}']
    args+=['-L',f'127.0.0.1:{a.local_port}:127.0.0.1:{a.remote_port}',a.destination,command]
    print('正在建立 GM 安全连接；SSH 登录由 OpenSSH 处理，密钥不会显示。',flush=True)
    child=subprocess.Popen(args,stdout=subprocess.PIPE,text=True,encoding='utf8',errors='replace')
    try:
        key=read_key(child,a.timeout)
        if child.poll() is not None:raise ValueError('SSH 连接已退出，请检查端口转发及登录状态')
        # A differing local port must be explicitly allowlisted using the
        # manager's --forwarded-port; the connector never changes that policy.
        webbrowser.open(f'http://127.0.0.1:{a.local_port}/#key={key}')
        del key
        print('GM 页面已打开。保持此窗口运行；按 Ctrl+C 断开管理连接，游戏服务不会关闭。',flush=True)
        if child.wait()!=0:raise ValueError('SSH 管理连接已中断，请检查网络后重新连接')
    except ValueError as e:raise SystemExit(str(e)) from None
    except KeyboardInterrupt:pass
    finally:
        close_ssh(child)
    return 0


if __name__=='__main__':raise SystemExit(main())
