"""Reuse guild publisher's native clock regression against this bound candidate."""
import bootstrap
from pathlib import Path
import hashlib,json,sys,types
source=Path('G:/els/analysis/guild-full-system-20261105-v1/verify_quest_clock_tls.py')
out=bootstrap.HERE/'inherited-guild-clock';out.mkdir(exist_ok=True)
sys.modules['overlay']=types.SimpleNamespace(BASE=bootstrap.BASE)
text=source.read_text(encoding='utf8')
text=text.replace('OUT = Path(__file__).resolve().parent','OUT = Path('+repr(str(out))+')')
text=text.replace("point = {'release':json.loads((OUT/'source.json').read_bytes())['release']+' + guild candidate'}",
    "point = {'release':"+repr(bootstrap.PIN['parent_release']+' + latency candidate')+'}')
text=text.replace('str(m.__file__)','str(m.__spec__.origin)').replace('Path(m.__file__)','Path(m.__spec__.origin)')
status=None
try:exec(compile(text,str(source),'exec'),dict(__name__='__main__',__file__=str(source)))
except SystemExit as error:status=error.code
assert status==0,dict(guild_clock_test_exit=status)
assert not bootstrap.FREE_THREADED_BUILD or not sys._is_gil_enabled()
(out/'binding.json').write_text(json.dumps(dict(passed=True,
    original_test_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    candidate_bindings=bootstrap.SOURCE_BINDINGS,parent=bootstrap.PIN,
    GIL_enabled=sys._is_gil_enabled()),indent=2),'utf8')
