"""Extend the related real relation/TLS regression with native167 persistence."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
raw=(W/'verify_relation_tls.py').read_text('utf8')
raw=raw.replace("B=W.parent/'duel-wire-v2/full-source';C=W/'candidate/els_server'","B=W/'full-source-v2';C=W/'candidate-v2/els_server'")
anchor='            await invite();rejected,_=await answer(False)'
assert raw.count(anchor)==1
added='''            from els_server.protocol.social_settings_messages import DEFAULT
            from els_server.storage import social_settings
            assert all(next(e for e in p.received if e.kind==0x2f).payload[8:18]==DEFAULT for p in peers)
            disabled=DEFAULT[:7]+b'\\0'+DEFAULT[8:]
            def preferences():return read('SELECT owner,payload,revision FROM native_social_settings ORDER BY owner')
            saved=await student.query(0x167,disabled)
            assert saved.payload==bytes(4)+disabled
            original_preferences=preferences();assert original_preferences==[(uid[1],disabled,1)]
            rejected=await teacher.query(0x1e8,struct.pack('>Q',uid[1]))
            assert struct.unpack_from('>i',rejected.payload)[0]==1979 and not app.world.mentors.pending
            for invalid in (disabled[:-1],disabled+b'\\0',bytes((2,))+disabled[1:]):
                rejected=await student.query(0x167,invalid)
                assert struct.unpack_from('>i',rejected.payload)[0]==1836 and preferences()==original_preferences
            again=await student.query(0x167,disabled);assert again.payload==bytes(4)+disabled and preferences()==original_preferences
            with patch.object(social_settings,'encode_event',side_effect=ValueError('Owned late settings encoder failure')):
                failed=await student.query(0x167,DEFAULT)
                assert struct.unpack_from('>i',failed.payload)[0]==1836 and preferences()==original_preferences
            report['checks'].append('Original2F preference slot;167/168 disables invitations server-side; malformed and repeated settings do not mutate; late encoding rolls back')
            await student.close();peers.remove(student)
            deadline=time.monotonic()+5
            while app.playing.get(values[1]['account_id'])is sessions[1]:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            student=await connect(values[1],peers);sessions[1]=app.playing[values[1]['account_id']]
            assert next(e for e in student.received if e.kind==0x2f).payload[8:18]==disabled
            assert next(e for e in outsider.received if e.kind==0x2f).payload[8:18]==DEFAULT
            restored=await student.query(0x167,DEFAULT)
            assert restored.payload==bytes(4)+DEFAULT and preferences()==[(uid[1],DEFAULT,2)]
            report['checks'].append('Actual TLS logout/reconnect restores disabled choice; other characters retain their own choice; native167 re-enables without economy changes')
'''
raw=raw.replace(anchor,added+anchor)
raw=raw.replace("'relation-tls-'","'social-settings-tls-'")
ast.parse(raw)
exec(compile(raw,str(W/'social-settings-TLS-scenario.py'),'exec'),{'__name__':'__main__','__file__':str(W/'social-settings-TLS-scenario.py')})
