"""Native support readiness, carried by the existing authenticated relay.

The owned probe publishes actual install/disable events in its launch attempt.
Neither this status nor a client build string supplies a health denominator.
"""
import json,uuid
from pathlib import Path
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
SOURCE_SHA='ac2c528f4f1a4bd881fa62b741404d8e6b24846b4540aae11c5986d96e92e6ec'
EMPTY=dict(version=1,ready=False,epoch=None,source_sha256=None)

def decode(payload):
    if not isinstance(payload,dict)or set(payload)!=set(EMPTY)or type(payload['version'])is not int or payload['version']!=1 or type(payload['ready'])is not bool:raise ValueError('PvP support status fields')
    epoch=payload['epoch'];source=payload['source_sha256']
    if epoch is not None and (not isinstance(epoch,str)or str(uuid.UUID(epoch))!=epoch):raise ValueError('PvP support epoch')
    if source is not None and(not isinstance(source,str)or len(source)!=64 or any(c not in'0123456789abcdef'for c in source)):raise ValueError('PvP support source digest')
    return dict(payload,ready=payload['ready']and epoch is not None and source==SOURCE_SHA)

def publish(path,event,game,client_sha256,source_path,epoch):
    """Only the actual probe's native ready/disabled callbacks call this."""
    import hashlib,os,psutil
    source=Path(source_path);probe=psutil.Process(os.getpid())
    value=dict(version=1,ready=event=='pvp_native_hp_source_ready',epoch=epoch,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),client_sha256=client_sha256,
        probe_pid=probe.pid,probe_created=probe.create_time(),game_pid=game.pid,game_created=psutil.Process(game.pid).create_time())
    target=Path(path);temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(value,separators=(',',':')),'utf8');temporary.replace(target)

def read_owned(path,owner_pid):
    """An old/missing/foreign/dead probe never enables the arena."""
    import psutil
    if path is None or owner_pid is None:return dict(EMPTY)
    p=Path(path)
    if not p.exists():return dict(EMPTY)
    try:
        if p.is_symlink()or p.stat().st_size>2048:raise ValueError('PvP support status file')
        value=json.loads(p.read_bytes());keys=set(EMPTY)|{'client_sha256','probe_pid','probe_created','game_pid','game_created'}
        if not isinstance(value,dict)or set(value)!=keys or value['client_sha256']!=EXE_SHA:raise ValueError('PvP support client identity')
        for name in('probe','game'):
            if type(value[name+'_pid'])is not int or type(value[name+'_created'])not in(int,float):raise ValueError('PvP support process identity')
        probe=psutil.Process(value['probe_pid']);game=psutil.Process(value['game_pid'])
        if (not probe.is_running()or not game.is_running()or probe.ppid()!=owner_pid or game.ppid()!=probe.pid
            or probe.create_time()!=value['probe_created']or game.create_time()!=value['game_created']
            or Path(game.exe()).name.lower()!='x2_dx11.exe'):raise ValueError('PvP support owned process generation')
        return decode({k:value[k]for k in EMPTY})
    except (OSError,ValueError,TypeError,KeyError,psutil.Error):return dict(EMPTY)
