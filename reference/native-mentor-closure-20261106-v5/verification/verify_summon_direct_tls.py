"""Use the witnessed original720→227 path, replacing the old225 assumption."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
raw=(W/'verify_summon_tls.py').read_text('utf8')
old="original=foundation.read_text('utf8');tree=ast.parse(original)"
assert raw.count(old)==1
raw=raw.replace(old,"original=foundation.read_text('utf8')\noriginal=original.replace(\"B=W.parent/'duel-wire-v2/full-source';C=W/'candidate/els_server'\",\"B=W/'full-source-v5';C=W/'candidate-v5/els_server'\")\ntree=ast.parse(original)")
raw=raw.replace("sessions[1].phase=='map_loading'","sessions[1].phase=='square_accepted'")
old="            assert (await student.query(0x225,struct.pack('>iB',location['map'],0))).payload[:4]==bytes(4)\n"
assert raw.count(old)==1;raw=raw.replace(old,'')
raw=raw.replace('wrong next225 denied; exact225/227 saves arrival','ordinary225 denied; original direct227 saves arrival')
raw=raw.replace("'summon-tls-'","'summon-direct-tls-'")
ast.parse(raw)
exec(compile(raw,str(W/'summon-direct-TLS-scenario.py'),'exec'),{'__name__':'__main__','__file__':str(W/'summon-direct-TLS-scenario.py')})
