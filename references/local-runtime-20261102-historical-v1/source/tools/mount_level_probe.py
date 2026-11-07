"""Read or set one mount's experimental level/exp; stamina is never touched."""
import argparse,sqlite3,sys
from contextlib import closing
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from els_server.storage import mount_progress
from els_server.protocol import mount_messages

def tail(mount):return mount_messages.record(mount)[-19:].hex()

def main():
 parser=argparse.ArgumentParser(description='Probe the opaque DE1310 tail level/exp slots.')
 parser.add_argument('database',help='existing player sqlite path (never created here)')
 parser.add_argument('uid',type=int);parser.add_argument('level',type=int);parser.add_argument('exp',type=int,nargs='?',default=0)
 parser.add_argument('--slot',choices=mount_progress.SLOTS,default='h',help='slot carrying level: h (2 bytes) or q (8 bytes)')
 args=parser.parse_args();path=Path(args.database)
 if not path.is_file():raise SystemExit('SQLite path does not exist: '+str(path))
 if not 0<args.uid<2**63:raise SystemExit('Invalid mount UID')
 if args.level<0 or args.exp<0:raise SystemExit('Invalid mount level/exp')
 base=dict(uid=args.uid,unit=0,name='')
 with closing(sqlite3.connect(path)) as db,db:
  before=mount_progress.load(db,args.uid)
  print('slot:',args.slot)
  print('mount_progress before:',before)
  print('tail before:',tail(dict(base,**before)))
  if args.level==0:mount_progress.clear(db,args.uid)
  else:mount_progress.set_level(db,args.uid,args.level,args.exp,args.slot)
  after=mount_progress.load(db,args.uid)
  print('mount_progress after:',after)
  merged={**base,**after};merged['slot']=args.slot
  print('tail after:',tail(merged))

if __name__=='__main__':main()
