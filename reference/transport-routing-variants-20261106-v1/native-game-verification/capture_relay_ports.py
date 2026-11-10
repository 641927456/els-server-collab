"""Inspect only the current owned bridge's UDP proxy sockets, without mutation."""
from pathlib import Path
import hashlib,json,re,sys,time
sys.dont_write_bytecode=True;sys.path.insert(0,'G:/els/tools/pylibs');import psutil
HERE=Path(__file__).resolve().parent
assert re.fullmatch(r'family1-v[0-9]+',sys.argv[1])
n=HERE/sys.argv[1];r=json.loads((n/'isolation-receipt.json').read_bytes());binding=json.loads((HERE/'runtime-binding.json').read_bytes())
assert not r.get('client_executable_unchanged')
game=psutil.Process(r['client_pid']);assert game.create_time()==r['client_created']
pids=r['job_membership_at_game_birth']['server_pids'];assert len(pids)==2
bridge=psutil.Process(pids[1]);args=bridge.cmdline();assert '-m'in args and args[args.index('-m')+1]=='els_server.friends_bridge'
assert Path(bridge.cwd()).resolve()==Path(binding['runtime']).resolve()
assert any((Path(parent.cwd())/arg).resolve()==(n/'probe_owned.py').resolve()
 for parent in bridge.parents()for arg in parent.cmdline()if arg.endswith('probe_owned.py'))
ports=sorted(c.laddr.port for c in bridge.net_connections(kind='udp')if c.laddr.ip=='127.0.0.1'and 21100<=c.laddr.port<=21131)
assert ports==list(range(21100,21131)),ports
file=Path(binding['runtime'])/'els_server/friends_relay.py'
report=dict(ok=True,owned_bridge_pid=bridge.pid,owned_bridge_created=bridge.create_time(),
 udp_proxy_ports=ports,own_native_slot=31,self_proxy_omitted_by_original_transport=True,
 client_transport_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
 observation='Actual31 UDP proxies require the selected32-member manifest; the installed8-member parser cannot produce this set',
 read_only=True,physical_input_actions=0,installed=False)
out=n/('owned-relay-ports-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,udp_proxies=len(ports),evidence=str(out))))
