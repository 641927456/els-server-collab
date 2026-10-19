"""Portable source/privacy/protocol checks; runtime validation is explicit."""
from pathlib import Path
import argparse,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def run(command):subprocess.run(command,cwd=ROOT,check=True)
def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true');args=parser.parse_args(argv)
    run([sys.executable,'-B',str(ROOT/'tools/repository_guard.py')])
    names=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf8').split('\0')
    count=0
    for name in filter(None,names):
        if Path(name).suffix in ('.py','.pyw'):
            compile((ROOT/name).read_text(encoding='utf-8-sig'),name,'exec');count+=1
    from els_server.protocol.protocol_codec import Keys,Event,encode_event,decode_event,encode_frame,decode_frame
    keys=Keys(os.urandom(8),os.urandom(8))
    event=Event(0x202,kind=0x6eb,payload=bytes(range(33)))
    plaintext=encode_event(event)
    wire=encode_frame(plaintext,keys,spi=7,sequence=1)
    frame=decode_frame(wire,keys,expected_sequence=1)
    assert decode_event(frame.plaintext)==event
    if args.with_runtime:
        run([sys.executable,'-B','-m','els_server','--config','config/server.toml','--check'])
        assert not (ROOT/'state/development.sqlite3').exists(),'CI must not create a player database'
    print(json.dumps(dict(ok=True,python_sources_compiled=count,protocol_roundtrip=True,runtime_check=args.with_runtime,no_owner_data=True)))

if __name__=='__main__':main()
