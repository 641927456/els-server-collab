from delivery_common import *
import subprocess,sys,re
c=read(W/'publication/release-contract.json')['local'];root=R/c['root']
assert read(W/'publication/local-install/qualification.json')['ok']
for row in c['delta']:assert sha(root/row['path'])==row['sha256']
t=(W/'test_ring_wear.py').read_text('utf8')
t,n=re.subn(r'^BASE=Path\(.*\)$',lambda m:'BASE=Path('+repr(str(root))+')',t,flags=re.M);assert n==1
t=t.replace("if '--baseline' not in sys.argv:","if False: # Exact installed runtime, no candidate module substitution")
p=W/'installed-local-session-test.py';p.write_text(t,'utf8')
q=subprocess.run([sys.executable,'-B',str(p),'test_actual_104_session_dispatch_and_105_response'],capture_output=True)
(W/'installed-local-session-test.log').write_bytes(q.stdout+q.stderr)
assert q.returncode==0,(q.stdout+q.stderr).decode(errors='replace')
save(W/'installed-local-session.json',dict(ok=True,actual_installed_root=str(root),candidate_substitution=False,tests=1,ACK105_rows=3,natural_GUI=False))
print('Actual installed LOCAL dispatcher and three-position ACK passed')
