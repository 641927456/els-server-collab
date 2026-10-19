"""A concurrent partial mailbox write is retried, never a client-launch failure."""
import json,sys,tempfile,os
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from probe_commands import read_command,write_command
with tempfile.TemporaryDirectory(prefix='commands-test-',dir=BASE/'analysis') as folder:
 p=Path(folder)/'command.json';stamp,value=read_command(p,None);assert stamp is None and value is None
 p.write_text('{"op":',encoding='utf8');assert read_command(p,None)==(None,None)
 partial_stamp=p.stat().st_mtime_ns
 p.write_text('{"op":"snapshot_skills"}',encoding='utf-8-sig');os.utime(p,ns=(partial_stamp,partial_stamp))
 stamp,value=read_command(p,None);assert value=={'op':'snapshot_skills'}
 assert read_command(p,stamp)==(stamp,None)
 write_command(p,{'op':'dungeon_action','action':0x377a,'argument':0})
 os.utime(p,ns=(partial_stamp,partial_stamp))  # Replacement must work with an identical mtime.
 stamp,value=read_command(p,stamp);assert value['action']==0x377a
 for bad in ('[]','{"op":2}','x'*8193):
  p.write_text(bad,encoding='utf8');assert read_command(p,None)[1] is None
print('PASS: missing, partial/same-mtime retry, BOM, atomic replacement and invalid diagnostic command records.')
