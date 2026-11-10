"""Teacher pending deletion must not prevent the student's real advancement."""
from pathlib import Path
W=Path(__file__).resolve().parent;base=W/'verify_career_proof_tls.py'
scope={'__file__':str(base),'__name__':'pending_teacher_fixture'}
exec(compile(base.read_text('utf8'),str(base),'exec'),scope)
source=scope['source']
anchor="                before=dump()\n                with patch.object(mail_attachment_messages,'detail'"
insertion=r'''
                if stage==1:
                    await teacher.close();peers.remove(teacher)
                    deadline=time.monotonic()+5
                    while app.playing.get(values[0]['account_id'])is sessions[0]:
                        assert time.monotonic()<deadline;await asyncio.sleep(.01)
                    from els_server.storage import character_lifecycle as lifecycle
                    from els_server.storage.character_selection import save as selection_save
                    selection_save(cfg.state_file,values[0]['account_id'],[0]*5,[uid[0]])
                    with patch.object(lifecycle,'current_time',return_value=int(time.time())+4*86400):
                        scheduled=lifecycle.change(cfg.state_file,values[0]['account_id'],uid[0],'schedule')
'''
assert source.count(anchor)==1
source=source.replace(anchor,insertion+anchor)
anchor="                mid=saved[0][1];claim_mail=struct.pack('>IQ',1,mid)+bytes(6)"
insertion=r'''
                if stage==1:
                    assert read('SELECT requested_at FROM character_lifecycle WHERE uid=?',(uid[0],))[0][0]>0
                    assert read('SELECT unit_class FROM characters WHERE uid=?',(uid[1],))==[(14,)]
                    with patch.object(lifecycle,'current_time',return_value=scheduled['restore_at']):
                        lifecycle.change(cfg.state_file,values[0]['account_id'],uid[0],'restore')
                    selection_save(cfg.state_file,values[0]['account_id'],[uid[0],0,0,0,0],[uid[0]])
                    teacher=await connect(values[0],peers);sessions[0]=app.playing[values[0]['account_id']]
                    report['checks'].append('Teacher actually scheduled for deletion and offline: student first-job219 still succeeds and creates one passive teacher mail; original restore and authenticated login make that exact mail claimable')
'''
assert source.count(anchor)==1
source=source.replace(anchor,insertion+anchor).replace("'career-proof-tls-'","'pending-teacher-tls-'")
generated=W/'generated-pending-teacher-main.py';generated.write_text(source+'\n','utf8')
exec(compile(source,str(generated),'exec'),scope)
if __name__=='__main__':raise SystemExit(not scope['asyncio'].run(scope['main']()))
