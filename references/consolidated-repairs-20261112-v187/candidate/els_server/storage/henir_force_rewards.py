"""Weekly stage fragments in original mailbox escrow, before cursor advance."""
from contextlib import closing
from pathlib import Path
import sqlite3,time
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item,item_body
from els_server.storage.manufacture_quota import window

ISSUANCE_ENABLED=True

def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='henir_force_rewards'").fetchone())
def recipient(db,mid):
    if not exists(db):return None
    row=db.execute('SELECT owner FROM henir_force_rewards WHERE mail_id=?',(mid,)).fetchone()
    return row[0]if row else None

def issue(path,owner,account,run,*,authorize,now=None):
    if not ISSUANCE_ENABLED:return []
    from els_server.domain.dungeon_routes import DungeonRun,route_catalog
    if type(run)is not DungeonRun or run.identity not in(38100,35880):raise ValueError('Henir original run required')
    mid=run.identity;mode=getattr(run,'henir_mode',1)if mid==38100 else 0;stage=run.round;count=(20 if mode==1 else 6)if mid==38100 else 5
    if (run.graph!=route_catalog().graph(mid)or len(run.rotation)!=count or not 0<=stage<count or not run.poll_ready()or not authorize()):raise ValueError('Henir completed current stage required')
    template,quantity=(190811,(stage//3+1)if mode==1 else(10,10,10,12,15,20)[stage])if mid==38100 else(62257,(1,3,6,10,20)[stage])
    now=int(time.time())if now is None else now;begin,_=window(now,region='CN')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,owner)
        if not authorize()or db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account,):raise ValueError('Henir reward owner/lease')
        from els_server.storage.game_mail import ensure
        ensure(db)
        ensure_mode_ledger(db)
        old=db.execute('SELECT period FROM henir_force_rewards WHERE owner=? AND dungeon=? AND mode=? AND stage=? AND period>=?',(owner,mid,mode,stage,begin)).fetchone()
        if old:
            if old[0]!=begin:raise ValueError('Henir weekly clock moved backwards')
            return []
        campaign=f'henir-force-{owner}-{mid}-{begin}-{stage}'if mode!=2 else f'henir-force-challenge-{owner}-{mid}-{begin}-{stage}'
        cur=db.execute('''INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at)VALUES(?,?,?,?,?,0,?,?)''',(campaign,account,'格雷夫','赫尼尔时空关卡奖励',f'本周第{stage+1}关卡奖励。可在格雷夫处兑换原力。',now,now+365*86400))
        mail=cur.lastrowid
        from els_server.storage.item_instances import next_uid
        from els_server.storage.mail_attachments import put
        item=validate_item(dict(uid=next_uid(db),template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],slot=0,count=quantity))
        item_body(item);put(db,mail,item,item)
        db.execute('INSERT INTO henir_force_rewards(owner,dungeon,period,stage,mail_id,run_id,mode) VALUES(?,?,?,?,?,?,?)',(owner,mid,begin,stage,mail,run.run_id,mode))
        from els_server.storage.player_mail import decorate
        from els_server.protocol.mail_attachment_messages import header,detail
        cur=db.execute('SELECT * FROM game_mail WHERE id=?',(mail,));row=dict(zip((x[0]for x in cur.description),cur.fetchone()));row=decorate(db,row,now=now);header(row);detail(row)
        from els_server.storage.online_2026_mail_snapshot import snapshot
        from els_server.protocol.mail_notifications_2026 import notice
        state=snapshot(db,account=account,character=owner,now=now)
        event=notice(unread_counts=state['unread_counts'],rows=[],flag=False)
        from els_server.protocol.protocol_codec import encode_event
        encode_event(event)
        if not authorize():raise ValueError('Henir stage authority expired')
        return [event]


def ensure_mode_ledger(db):
    definition="""CREATE TABLE IF NOT EXISTS henir_force_rewards(
        owner INTEGER NOT NULL,dungeon INTEGER NOT NULL,period INTEGER NOT NULL,
        stage INTEGER NOT NULL,mail_id INTEGER NOT NULL UNIQUE REFERENCES game_mail(id),
        run_id TEXT NOT NULL,mode INTEGER NOT NULL,
        PRIMARY KEY(owner,dungeon,mode,period,stage))"""
    if exists(db) and 'mode' not in {r[1] for r in db.execute('PRAGMA table_info(henir_force_rewards)')}:
        # Called within the real reward transaction; a failed issuance restores
        # the old schema and rows as well as the mail/attachment writes.
        db.execute('ALTER TABLE henir_force_rewards RENAME TO henir_force_rewards_mode_migration')
        db.execute(definition)
        db.execute("""INSERT INTO henir_force_rewards
            SELECT owner,dungeon,period,stage,mail_id,run_id,
                   CASE WHEN dungeon=38100 THEN 1 ELSE 0 END
            FROM henir_force_rewards_mode_migration""")
        db.execute('DROP TABLE henir_force_rewards_mode_migration')
    else:db.execute(definition)
