"""Attach only to our freshly created host, verify hook/reload/detach, then exit."""
import argparse,json,pathlib,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--native-root',type=pathlib.Path,required=True);args=p.parse_args()
sys.path.insert(0,str(args.native_root/'tools/pylibs'));import frida
here=pathlib.Path(__file__).resolve().parent
process=subprocess.Popen([sys.executable,'-B',str(here/'hook_child.py'),str(args.native_root/'analysis/client-6c6b5180/x2-runtime.bin')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
session=None
try:
    hello=json.loads(process.stdout.readline());assert hello['ready']and hello['owned_native_window']
    def call(expected,current):
        process.stdin.write(json.dumps([expected,current])+'\n');process.stdin.flush()
        return json.loads(process.stdout.readline())['result']
    assert call(4,5)==0 and call(5,4)==0 and call(4,4)==1
    session=frida.attach(process.pid)
    source=(here.parent/'client-support/challenge-scroll-open.js').read_text().split('// BEGIN production bootstrap')[0]
    source+='\nconst base=ptr('+repr(hello['base'])+');const first=installChallengeScrollSupport(base);rpc.exports={again(){return first===installChallengeScrollSupport(base);},remove(){first.detach();}};'
    script=session.create_script(source);errors=[];script.on('message',lambda m,data:errors.append(m)if m.get('type')=='error'else None);script.load();assert not errors
    assert script.exports_sync.again()and call(4,5)==1 and call(5,4)==1 and call(3,5)==0 and call(3,3)==1
    script.exports_sync.remove();assert call(4,5)==0 and call(5,4)==0 and call(4,4)==1
    print(json.dumps(dict(ok=True,isolated_native_process=True,actual_game=False,signature_guards=True,both_categories=True,unrelated_comparison_preserved=True,repeated_install=True,detach_restored=True)))
finally:
    if session is not None:session.detach()
    if process.poll()is None:
        process.stdin.write('"exit"\n');process.stdin.flush()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
    if process.returncode:raise RuntimeError(process.stderr.read())
