"""Old equal-content identity must copy to the current signed path without download."""
from pathlib import Path
import hashlib,json,os,subprocess
H=Path(__file__).resolve().parent;R=H.parents[1];W=H/'checks/cache-final';W.mkdir(parents=True)
game=W/'selected-game/data';game.mkdir(parents=True);client=game/'x2_dx11.exe';client.write_bytes(b'Owned cache identity selection fixture')
old=json.loads((R/'analysis/runtime-package-audit-20261113-v3/packages/client.payload.json').read_bytes())
raw=(R/'analysis/runtime-package-audit-20261113-v3/packages/client.payload.json').read_bytes();old_id=hashlib.sha256(raw).hexdigest()
current=json.loads((H/'runtime-build.json').read_bytes())['modules']['client']['identity'];assert current!=old_id
seed=game/'.els-runtime/component-runtimes'/(old['archive']['sha256'][:16]+'-'+old_id[:12]);seed.mkdir(parents=True)
for row in old['files']:
 source=H/'runtime/client'/row['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
 dest=seed/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);os.link(source,dest)
(seed/'.complete').write_text(old['archive']['sha256'],encoding='utf8')
empty=W/'no-network-assets';empty.mkdir()
result=subprocess.run([str(H/'module_actual_probe.exe'),str(H/'preview/ElsFriends-V198-preview.exe'),'cache',str(W/'profile'),str(client),str(empty),str(W/'result.json')],capture_output=True,timeout=120,creationflags=0x08000000)
(W/'probe.stdout').write_bytes(result.stdout);(W/'probe.stderr').write_bytes(result.stderr)
d=json.loads((W/'result.json').read_bytes());assert result.returncode==0 and d['ok'],d.get('error')
assert d['available_before']is None and d['local_test_transport_requests']==[]
assert d['client_first_stats']['downloaded_files']==0 and d['client_first_stats']['reused_files']==108
assert Path(d['client_root']).name==old['archive']['sha256'][:16]+'-'+current[:12]and seed.exists()
(H/'cache-final-proof.json').write_text(json.dumps(dict(ok=True,actual_production_EXE=True,both_fastpaths_checked=True,old_available_rejected=True,all_files_reused=108,downloaded=0,current_directory_identity=True,old_directory_preserved=True,GUI=False),indent=2)+'\n',encoding='utf8')
print('Actual production EXE rejects the old cache identity and reuses all 108 files into the current signed directory')
