"""Character-bound campaign ledger; all mutations use the caller's transaction."""
import json, uuid
from datetime import datetime,timedelta,timezone
from els_server.domain import abyss_weapon_2026 as rules
from els_server.storage.inventory_state import grant_items,load_items

def exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())
def week(now):
    local=datetime.fromtimestamp(now,timezone(timedelta(hours=8)))
    start=local.replace(hour=10,minute=0,second=0,microsecond=0)-timedelta(days=(local.weekday()-2)%7)
    if local<start:start-=timedelta(days=7)
    return int(start.timestamp())
def period(quest,now):return week(now)if quest==169590 else 0

class Campaign:
    def __init__(self,db):self.db=db
    def _inventory_changed(self,character):
        updated=self.db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?AND revision<?',(character,2**63-1))
        if updated.rowcount!=1:raise ValueError('Abyss inventory revision cannot advance')
    def initialize(self):
        # The caller holds one write transaction, including the legacy upgrade.
        legacy=any(r[1]=='character' and r[5]==0 for r in self.db.execute('PRAGMA table_info(abyss2026_accounts)'))
        if legacy:
            self.db.execute('ALTER TABLE abyss2026_tasks RENAME TO abyss2026_tasks_account_v1')
            self.db.execute('ALTER TABLE abyss2026_accounts RENAME TO abyss2026_accounts_account_v1')
        self.db.execute('''CREATE TABLE IF NOT EXISTS abyss2026_accounts(
            account INTEGER NOT NULL,character INTEGER NOT NULL,joined_at INTEGER NOT NULL,
            box_uid INTEGER NOT NULL,weapon_uid INTEGER NOT NULL DEFAULT 0,
            points INTEGER NOT NULL DEFAULT 0 CHECK(points BETWEEN 0 AND 500),
            rewards_mask INTEGER NOT NULL DEFAULT 0 CHECK(rewards_mask BETWEEN 0 AND 31),
            converted_uid INTEGER NOT NULL DEFAULT 0,definition_sha TEXT NOT NULL,
            PRIMARY KEY(account,character))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS abyss2026_tasks(
            account INTEGER NOT NULL,character INTEGER NOT NULL,quest INTEGER NOT NULL,period INTEGER NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,claimed_at INTEGER,
            PRIMARY KEY(account,character,quest,period))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS abyss2026_runs(
            run TEXT PRIMARY KEY,account INTEGER NOT NULL,character INTEGER NOT NULL,
            dungeon INTEGER NOT NULL,period INTEGER NOT NULL,appropriate INTEGER NOT NULL,
            consumed_proof TEXT)''')
        if legacy:
            self.db.execute('INSERT INTO abyss2026_accounts SELECT * FROM abyss2026_accounts_account_v1')
            self.db.execute("""INSERT INTO abyss2026_tasks(account,character,quest,period,count,claimed_at)
                SELECT t.account,a.character,t.quest,t.period,t.count,t.claimed_at
                FROM abyss2026_tasks_account_v1 t LEFT JOIN abyss2026_accounts_account_v1 a ON a.account=t.account""")
            self.db.execute('DROP TABLE abyss2026_tasks_account_v1')
            self.db.execute('DROP TABLE abyss2026_accounts_account_v1')
    def owner(self,account,character):
        from els_server.domain.character_rules import CLASSES
        row=self.db.execute('SELECT c.unit_class,c.level FROM characters c JOIN character_owners o ON c.uid=o.uid WHERE c.uid=? AND o.account_id=?',(character,account)).fetchone()
        if row is None or row[1]!=99 or CLASSES[row[0]]['stage']!=3:raise ValueError('Owned level99 third-job participant required')
        return row[0]
    def snapshot(self,account,character):
        row=self.db.execute('SELECT character,joined_at,box_uid,weapon_uid,points,rewards_mask,converted_uid,definition_sha FROM abyss2026_accounts WHERE account=? AND character=?',(account,character)).fetchone()
        if row is None:return None
        if row[-1]!=rules.DEFINITION_SHA:raise ValueError('Saved Abyss definition differs')
        return dict(zip(('character','joined_at','box_uid','weapon_uid','points','rewards_mask','converted_uid'),row[:-1]))
    def participant(self,account,character):
        self.owner(account,character);row=self.snapshot(account,character)
        if row is None:raise ValueError('This character has not joined the Abyss campaign')
        return row
    def join(self,account,character,now):
        from els_server.domain.gm_events import ABYSS_WEAPON, require_open
        self.owner(account,character);old=self.snapshot(account,character)
        if old is not None:return []
        require_open(ABYSS_WEAPON, now)
        updates=grant_items(self.db,rules.reward_plan(7791),character)
        if len(updates)!=1:raise ValueError('One Abyss weapon box required')
        self.db.execute('INSERT INTO abyss2026_accounts(account,character,joined_at,box_uid,definition_sha)VALUES(?,?,?,?,?)',
                        (account,character,now,updates[0]['uid'],rules.DEFINITION_SHA))
        self.refresh(account,character,now)
        self._inventory_changed(character)
        return updates
    def tasks(self,account,character,now):
        row=self.snapshot(account,character)
        if row is None:return []
        return [dict(id=q,count=self.db.execute('SELECT count,claimed_at FROM abyss2026_tasks WHERE account=? AND character=? AND quest=? AND period=?',(account,character,q,period(q,now))).fetchone())for q in rules.quests()]
    def refresh(self,account,character,now):
        self.participant(account,character)
        for q in rules.quests():self.db.execute('INSERT OR IGNORE INTO abyss2026_tasks(account,character,quest,period)VALUES(?,?,?,?)',(account,character,q,period(q,now)))
        facts={}
        if exists(self.db,'title_ownership'):
            from els_server.storage.titles import character as title_character,owned
            owned_titles={r['title']for r in owned(self.db,title_character(self.db,character),now)if r['expires_at']==0}
            for q,t in ((169530,2050),(169540,2160),(169550,2210)):facts[q]=int(t in owned_titles)
        if exists(self.db,'boosting2026_participation'):
            bound=self.db.execute('SELECT character FROM boosting2026_participation WHERE account=?',(account,)).fetchone()
            facts[169570]=int(bound==(character,))
            if bound==(character,)and exists(self.db,'boosting2026_task_rewards'):
                facts[169580]=int(bool(self.db.execute('SELECT 1 FROM boosting2026_task_rewards WHERE account=? AND character=? AND quest=169514',(account,character)).fetchone()))
        for q,n in facts.items():self.db.execute('UPDATE abyss2026_tasks SET count=max(count,?) WHERE account=? AND character=? AND quest=? AND period=0',(n,account,character,q))
    def admit(self,account,character,run,dungeon,appropriate,now):
        self.participant(account,character)
        if str(uuid.UUID(run))!=run:raise ValueError('Authoritative run UUID required')
        if exists(self.db,'reward_receipts')and self.db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(run,)).fetchone():raise ValueError('Cannot admit an already rewarded run')
        values=(account,character,dungeon,week(now),int(appropriate))
        old=self.db.execute('SELECT account,character,dungeon,period,appropriate FROM abyss2026_runs WHERE run=?',(run,)).fetchone()
        if old is not None:
            if old!=values:raise ValueError('Conflicting Abyss run admission')
            return
        self.db.execute('INSERT INTO abyss2026_runs VALUES(?,?,?,?,?,?,NULL)',(run,*values))
    def recover(self,account,character,now):
        self.refresh(account,character,now)
        if not exists(self.db,'reward_receipts'):return
        for run,dungeon,run_week,appropriate,digest,raw in self.db.execute('''SELECT r.run,r.dungeon,r.period,r.appropriate,p.proof_sha256,p.grant_json
                FROM abyss2026_runs r JOIN reward_receipts p ON r.run=p.run_id
                WHERE r.account=? AND r.character=? AND r.consumed_proof IS NULL''',(account,character)).fetchall():
            receipt=json.loads(raw)
            if receipt.get('owner',1001)!=character or not isinstance(receipt.get('dungeon_clear'),list)or receipt['dungeon_clear'][0]!=dungeon:raise ValueError('Abyss committed clear owner/map differs')
            for q in (169520,169560,169590):
                cond=rules.quests()[q]['objective']['m_ClearCondition']
                admitted=(appropriate and dungeon not in cond['m_eExceptionDungeonID'].values())if q==169520 else dungeon in cond['m_eDungeonID'].values()
                p=run_week if q==169590 else 0
                if admitted:self.db.execute('UPDATE abyss2026_tasks SET count=min(count+1,?)WHERE account=? AND character=? AND quest=? AND period=? AND claimed_at IS NULL',(rules.limit(q),account,character,q,p))
            self.db.execute('UPDATE abyss2026_runs SET consumed_proof=? WHERE run=?',(digest,run))
    def claim_task(self,account,character,quest,now):
        self.participant(account,character);self.recover(account,character,now)
        row=self.db.execute('SELECT count,claimed_at FROM abyss2026_tasks WHERE account=? AND character=? AND quest=? AND period=?',(account,character,quest,period(quest,now))).fetchone()
        if row is None or row[0]!=rules.limit(quest):raise ValueError('Abyss task is not complete')
        if row[1]is None:
            self.db.execute('UPDATE abyss2026_tasks SET claimed_at=? WHERE account=? AND character=? AND quest=? AND period=?',(now,account,character,quest,period(quest,now)))
            self.db.execute('UPDATE abyss2026_accounts SET points=min(points+?,500)WHERE account=? AND character=?',(rules.points()[quest],account,character))
        return row[1]if row[1]is not None else now
    def claim_reward(self,account,character,index):
        row=self.participant(account,character)
        if index not in range(5):raise ValueError('Unknown Abyss reward index')
        bit=1<<index
        if row['rewards_mask']&bit:return []
        if row['points']<(index+1)*100 or row['rewards_mask']!=(bit-1):raise ValueError('Claim earlier qualified Abyss rewards first')
        reward=rules.definition()['client_config']['PointsRequiredToReceiveReward'][str(index+1)]['RewardID']
        updates=grant_items(self.db,rules.reward_plan(reward),character)
        self.db.execute('UPDATE abyss2026_accounts SET rewards_mask=rewards_mask|? WHERE account=? AND character=?',(bit,account,character))
        self._inventory_changed(character)
        return updates
    def convert(self,account,character,now):
        row=self.participant(account,character)
        if row['points']!=500 or row['rewards_mask']!=31:raise ValueError('All five Abyss rewards required')
        item=next((i for i in load_items(self.db,character)if i['uid']==row['weapon_uid']),None)
        if item is None or item['template']not in rules.weapon_templates() or item['count']!=1:raise ValueError('Exact bound Abyss weapon required')
        if row['converted_uid']:
            if 'expires_at'in item:raise ValueError('Converted weapon has an unexpected deadline')
            return item
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=now);require_unlocked(item)
        if 'expires_at'not in item:raise ValueError('Timed Abyss weapon required')
        self.db.execute('DELETE FROM item_expiration WHERE item_uid=?',(item['uid'],))
        self.db.execute('UPDATE abyss2026_accounts SET converted_uid=?WHERE account=? AND character=?',(item['uid'],account,character))
        self._inventory_changed(character)
        return next(i for i in load_items(self.db,character)if i['uid']==item['uid'])
