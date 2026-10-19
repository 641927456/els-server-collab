"""Isolated synthetic mail-scope regression; no producer, player save or server used."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from els_server.storage import game_mail,mailbox_extras

def main():
    with tempfile.TemporaryDirectory(prefix='kink-mail-scope-') as temporary:
        path=Path(temporary)/'synthetic.sqlite3'
        with closing(sqlite3.connect(path)) as db,db:
            game_mail.ensure(db)
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,name TEXT NOT NULL)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.executemany('INSERT INTO characters VALUES (?,?)',[(1001,'FixtureA'),(1002,'FixtureB')])
            db.executemany('INSERT INTO character_owners VALUES (?,?)',[(1001,2),(1002,2)])
            db.execute('''CREATE TABLE online2026_mail_scope(
                mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),account_id INTEGER NOT NULL,
                recipient_uid INTEGER NOT NULL,deadline INTEGER NOT NULL)''')
            db.execute('''INSERT INTO game_mail(id,campaign,account_id,sender,title,body,ed,created_at,expires_at)
                VALUES(1,'synthetic-scope',2,'Fixture','Scope fixture','Synthetic only',0,100,1000)''')
            db.execute('INSERT INTO online2026_mail_scope VALUES(1,2,1002,1000)')
        counts={uid:game_mail.inbox(path,2,uid,now=200)[0] for uid in (1001,1002)}
        status={uid:mailbox_extras.status(path,2,uid,now=200) for uid in (1001,1002)}
        ok=counts[1001]==0 and status[1001]==(0,0,0) and counts[1002]==1 and status[1002]==(1,1,1)
        print(json.dumps({'ok':ok,'inbox_count':counts,'status_count_unread_last':status,
            'expected_A':[0,0,0],'expected_B':[1,1,1],
            'fixture':'same account; synthetic role-scoped metadata; no event producer or attachments',
            'production_database_used':False,'network_or_game_used':False},indent=2))
        return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
