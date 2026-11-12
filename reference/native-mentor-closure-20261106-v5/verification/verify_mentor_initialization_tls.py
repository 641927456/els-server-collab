"""Actual2F cold restoration of a persisted partner, on the related TLS case."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent;raw=(W/'verify_relation_tls.py').read_text('utf8')
raw=raw.replace("B=W.parent/'duel-wire-v2/full-source';C=W/'candidate/els_server'","B=W/'full-source-v4';C=W/'candidate-v4/els_server'")
needle="            assert any(e.kind==0x1e7 and struct.unpack_from('>Q',e.payload,1)[0]==uid[0]for e in student.received)"
assert raw.count(needle)==1
added='''
            initial=next(e for e in student.received if e.kind==0x2f).payload
            assert struct.unpack_from('>I',initial,27)[0]==1
            with closing(sqlite3.connect(cfg.state_file))as db:
                saved=storage.relation(db,uid[1]);expected=wire.public_info(storage.public_info(db,uid[0],sessions[0],saved=saved))
            assert initial[31:31+len(expected)+4]==expected+bytes(4)
            assert struct.unpack_from('>I',next(e for e in outsider.received if e.kind==0x2f).payload,27)[0]==0
            report['checks'].append('Actual persisted student reconnect has one original2F/DD90A0 partner record; byte-exact native public info and empty supplemental string; unrelated role has zero records')
'''
raw=raw.replace(needle,needle+added)
raw=raw.replace("'relation-tls-'","'mentor-initialization-tls-'")
ast.parse(raw)
exec(compile(raw,str(W/'mentor-initialization-TLS-scenario.py'),'exec'),{'__name__':'__main__','__file__':str(W/'mentor-initialization-TLS-scenario.py')})
