"""Reuse the proven owned suspended-Job and input-denial native harness."""
from pathlib import Path
import ast,hashlib,json,sys
HERE=Path(__file__).resolve().parent;W=HERE.parents[1]
raw=(W/'duel-native-game-v1/prepare_attempt.py').read_text('utf8')
raw=raw.replace("parent=HERE.parent/'guild-native-game-v2'","parent=Path("+repr(str(W/'guild-native-game-v2'))+")")
raw=raw.replace('HERE=Path(__file__).resolve().parent;parent=','HERE=Path('+repr(str(HERE))+');parent=')
old='0x17a2d0:16,0x2d75c90:16,0x2d773e0:16,0x7e3d90:16,0xc97790:16,0x7d57a0:16,0x316c540:16,0x316e410:16,0xc90480:16'
assert raw.count(old)==1
raw=raw.replace(old,'0xbdeab0:16,0xc63d60:16,0x3286550:16,0x328f7d0:16,0x21460e0:16,0x2460890:16,0x3287520:16,0x74ffa0:16,0x2451350:16,0x2daf6b0:16,0x244d960:16,0x244b250:16')
raw=raw.replace('Owned native duel lifecycle qualification','Owned native housing actor and pet lifecycle qualification')
raw=raw.replace("original_native_accept_function='B77740 caseC21 ->B7B2E7 ->2D773E0',native_project_functions=244",
 "original_native_entry_function='BDEAB0 current-State action ->C63D60 with original924 pending',native_project_functions=468")
ast.parse(raw)
exec(compile(raw,str(HERE/'scenario-generator.py'),'exec'),{'__name__':'__main__','__file__':str(HERE/'scenario-generator.py')})
attempt=HERE/sys.argv[2]
source=(HERE/'server_owned.py').read_text('utf8').replace('HERE=Path(__file__).resolve().parent','HERE=Path('+repr(str(HERE))+')')
(attempt/'server_input.py').write_text(source,'utf8')
probe=attempt/'probe_owned.py';source=probe.read_text('utf8')
for a,b in(("str(N.parent/'server_owned.py')","str(N/'server_input.py')"),('time.monotonic()-start<240','time.monotonic()-start<300'),
 ("receipt['candidate_published']=True","receipt['candidate_published']=False")):
 assert source.count(a)==1,(a,source.count(a));source=source.replace(a,b)
ast.parse(source);probe.write_text(source,'utf8')
p=attempt/'preparation.json';v=json.loads(p.read_bytes());v.update(candidate_published=False,
 harness_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),backend_sha256=hashlib.sha256((attempt/'server_input.py').read_bytes()).hexdigest(),
 total_bound_seconds=300,preparation_bound_seconds=40,production_request_timeout_seconds=25,owned_input_controls_unchanged=True,natural_GUI=False)
p.write_text(json.dumps(v,indent=2)+'\n','utf8')
(attempt/'observer-input.js').write_bytes((HERE/'observer.js').read_bytes())
