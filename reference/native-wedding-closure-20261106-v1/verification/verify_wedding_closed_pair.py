"""The shared couple closure must not leave a publicly enterable ghost row."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
source=(W/'verify_reservation_mail.py').read_text('utf8');tree=ast.parse(source)
node=next(n for n in tree.body if isinstance(n,ast.Try))
prefix='\n'.join(source.splitlines()[:node.lineno-1]).replace("prefix='owned-reservation-mail-'","prefix='owned-wedding-closed-pair-'")
body=ast.get_source_segment(source,node);body=body[:body.index('    before=dump()')]
cases=r'''
    from els_server.storage import couple_closures
    book()
    def listed():
        with closing(sqlite3.connect(path))as db:
            db.execute('BEGIN');return weddings.lobby(db,1,now=now)
    assert len(listed()[0])==1
    with closing(sqlite3.connect(path))as db:
        expected=couple_closures.quote(db,1001,1)
    def close_pair():
        with closing(sqlite3.connect(path))as db,db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            return couple_closures.perform(db,1001,1,b'','owned-pre-wedding-farewell',expected,
                guard=guard,encode=lambda repeat:[rel.farewell_ack()],now=now+1)
    before=dump()
    with patch.object(rel,'farewell_ack',side_effect=ValueError('Owned late farewell encoder')):
        try:close_pair()
        except ValueError as error:assert str(error)=='Owned late farewell encoder'
        else:raise AssertionError('Late closure accepted')
    assert dump()==before and len(listed()[0])==1
    with closing(sqlite3.connect(path))as db:
        money=db.execute('SELECT *FROM reward_balances ORDER BY uid').fetchall()
        inventory=db.execute('SELECT *FROM inventory_items ORDER BY uid').fetchall()
        booking=db.execute('SELECT *FROM native_wedding_bookings').fetchall()
    assert close_pair()[0].payload==bytes(4)
    assert listed()==([],1)
    with closing(sqlite3.connect(path))as db:
        assert relationships.snapshot(db,1001,1)is None
        assert relationships.snapshot(db,bride,2)is None
        assert db.execute('SELECT *FROM reward_balances ORDER BY uid').fetchall()==money
        assert db.execute('SELECT *FROM inventory_items ORDER BY uid').fetchall()==inventory
        assert db.execute('SELECT *FROM native_wedding_bookings').fetchall()==booking
        assert db.execute('SELECT COUNT(*)FROM native_relationship_mail').fetchone()==(8,)
    before=dump();assert close_pair()[0].payload==bytes(4)and dump()==before
    report['checks'].append('Actual accepted couple, ring-debited booking and real parcel mail: failed farewell encoding retains active lobby; successful free couple1 closure hides old booking before pagination without rewriting reservation history, refunding ring/ED, changing inventory or reminting mail; replay stays closed')
    report.update(ok=True,native_Game=False,server_lobby_and_shared_closure_qualified=True)
'''
tail=source[source.index('except Exception:',source.index('try:\n')):]
tail=tail.replace("startswith('owned-reservation-mail-')","startswith('owned-wedding-closed-pair-')").replace("'reservation-mail-'","'wedding-closed-pair-'")
generated=W/'generated-wedding-closed-pair.py';text=prefix+'\n'+body+cases+'\n'+tail
ast.parse(text);generated.write_text(text,'utf8');exec(compile(text,str(generated),'exec'),globals())
