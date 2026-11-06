"""Caller-owned reward deliveries; no client route or campaign qualification bypass.

The activity controller must qualify the claim and commit its stamp/binding and
this delivery in one outer transaction. Attendance uses account mail;8173 uses
the bound character inventory. No game/GM endpoint grants by arbitrary RewardID.
"""
import contextlib,hashlib,json,uuid
from els_server.domain.activity_2026_rewards import ActivityRewards
from els_server.storage.inventory_state import grant_items,load_items

class RewardDelivery:
    def __init__(self,db,catalog):
        if type(catalog) is not ActivityRewards:raise TypeError('Verified local rewards required')
        self.db=db;self.catalog=catalog

    def _transaction(self):
        if not self.db.in_transaction:raise ValueError('Caller-owned activity transaction required')

    @contextlib.contextmanager
    def _savepoint(self):
        self._transaction();name='activity_reward_'+uuid.uuid4().hex;self.db.execute('SAVEPOINT '+name)
        try:yield;self.db.execute('RELEASE '+name)
        except BaseException:
            self.db.execute('ROLLBACK TO '+name);self.db.execute('RELEASE '+name);raise

    def initialize(self):
        self._transaction()
        self.db.execute('''CREATE TABLE IF NOT EXISTS activity2026_reward_deliveries(
            account INTEGER NOT NULL,reward_id INTEGER NOT NULL,character INTEGER NOT NULL,
            delivery TEXT NOT NULL,catalog_sha256 TEXT NOT NULL,payload_sha256 TEXT NOT NULL,
            resource_json TEXT NOT NULL,created_at INTEGER NOT NULL,
            PRIMARY KEY(account,reward_id))''')
        from els_server.storage.game_mail import ensure
        ensure(self.db)

    def _owner(self,account,character,minimum):
        self._transaction()
        if any(type(v) is not int or v<=0 for v in (account,character)):raise ValueError('Authenticated identity required')
        row=self.db.execute('SELECT level FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(character,account)).fetchone()
        if row is None or row[0]<minimum:raise ValueError('Owned eligible character required')

    @staticmethod
    def _time(now):
        if type(now) is not int or not 0<=now<2**63:raise ValueError('Server timestamp required')

    def _digest(self,data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

    def _previous(self,account,rid,kind,digest):
        row=self.db.execute('SELECT delivery,catalog_sha256,payload_sha256,resource_json FROM activity2026_reward_deliveries WHERE account=? AND reward_id=?',(account,rid)).fetchone()
        if row is None:return None
        if row[:3]!=(kind,self.catalog.digest,digest):raise ValueError('Reward delivery retry conflicts with saved definition')
        return json.loads(row[3])

    def _record(self,account,rid,character,kind,digest,resource,now):
        self.db.execute('INSERT INTO activity2026_reward_deliveries VALUES (?,?,?,?,?,?,?,?)',(account,rid,character,kind,self.catalog.digest,digest,json.dumps(resource,separators=(',',':')),now))

    def participation(self,*,account,character,now,qualified,encode):
        self._owner(account,character,99);self._time(now)
        if qualified is not True or not callable(encode):raise ValueError('Trusted activity qualification and encoder required')
        bound=self.db.execute('SELECT campaign,character FROM boosting2026_participation WHERE account=?',(account,)).fetchone()
        if bound!=(678,character):raise ValueError('Current immutable activity binding required')
        plan=self.catalog.plan(8173);digest=self._digest([character,8173,plan])
        with self._savepoint():
            uids=self._previous(account,8173,'character_inventory',digest);replayed=uids is not None
            if uids is None:
                uids=[i['uid'] for i in grant_items(self.db,plan,character)];self._record(account,8173,character,'character_inventory',digest,uids,now)
            items=load_items(self.db,character);out=dict(replayed=replayed,updates=[i for i in items if i['uid'] in uids],items=items)
            response=encode(out)
            if type(response) is not bytes or not 1<=len(response)<=65536:raise ValueError('Invalid committed reward response')
            return dict(out,response=response)

    def attendance_mail(self,*,account,character,reward_id,now,deadline,qualified,sender,title,body):
        self._owner(account,character,10);self._time(now);self._time(deadline)
        if qualified is not True or type(reward_id) is not int or not 8127<=reward_id<=8168 or deadline<=now:
            raise ValueError('Qualified selected attendance reward and future deadline required')
        from els_server.storage.game_mail import _text
        sender=_text(sender,24);title=_text(title,80);body=_text(body,2000)
        row=self.catalog.rewards[reward_id];plan=self.catalog.plan(reward_id)
        if len(plan)!=1:raise ValueError('One original attendance attachment required')
        digest=self._digest([reward_id,plan,deadline,sender,title,body])
        with self._savepoint():
            mid=self._previous(account,reward_id,'account_mail',digest)
            if mid is not None:
                if not self.db.execute('SELECT 1 FROM game_mail WHERE id=? AND account_id=?',(mid,account)).fetchone():raise ValueError('Lost original reward mail; no reissue')
                return dict(mail_id=mid,replayed=True)
            campaign='attendance2026-'+self._digest([account,reward_id])
            mid=self.db.execute('INSERT INTO game_mail(campaign,account_id,sender,title,body,ed,created_at,expires_at) VALUES (?,?,?,?,?,0,?,?)',(campaign,account,sender,title,body,now,deadline)).lastrowid
            from els_server.storage.item_instances import next_uid
            from els_server.storage.mail_attachments import put
            p=plan[0];item=dict(uid=next_uid(self.db),template=p['template'],metadata=p['metadata'],group=p['group'],slot=0,count=p['quantity'])
            # Announcement removes Cobo event items at campaign maintenance;
            # Luriel/ordinary rewards remain after claiming. Mail always expires.
            if row['source_name'].startswith('[科宝]'):item['expires_at']=deadline
            put(self.db,mid,item,item);self._record(account,reward_id,character,'account_mail',digest,mid,now)
            return dict(mail_id=mid,replayed=False)

    def retire_expired_mail(self,*,now):
        self._transaction();self._time(now)
        with self._savepoint():
            ids=[r[0] for r in self.db.execute('SELECT g.id FROM game_mail g JOIN activity2026_reward_deliveries r ON r.delivery=? AND r.account=g.account_id AND r.resource_json=cast(g.id AS TEXT) WHERE g.deleted_at IS NULL AND g.expires_at<=?',('account_mail',now))]
            for mid in ids:
                self.db.execute('UPDATE player_mail_items SET expired_at=? WHERE mail_id=? AND claimed_at IS NULL AND expired_at IS NULL',(now,mid))
                self.db.execute('UPDATE game_mail SET deleted_at=? WHERE id=? AND deleted_at IS NULL',(now,mid))
            return ids
