"""Small diagnostic mailbox; an in-progress write must not close the game."""
import hashlib,json,os
from pathlib import Path

def read_command(path,last_stamp):
    path=Path(path)
    try:
        # Atomic replacements can share an mtime on Windows. Read one bounded
        # file handle and include identity/content, so a new command isn't lost.
        with path.open(encoding='utf-8-sig') as handle:
            raw=handle.read(8193)
            info=os.fstat(handle.fileno())
        stamp=(info.st_mtime_ns,info.st_ino,hashlib.sha256(raw.encode('utf8')).digest())
        if stamp==last_stamp:return last_stamp,None
        if len(raw)>8192:return stamp,None
        value=json.loads(raw)
        if not isinstance(value,dict) or not isinstance(value.get('op'),str):return stamp,None
        return stamp,value
    except (OSError,UnicodeError,json.JSONDecodeError):
        return last_stamp,None  # Retry once the writer finishes, including the same mtime.

def write_command(path,value):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value),encoding='utf8');os.replace(temp,path)
