"""Server-local automatic daily clear tasks, authorized 2026-11-07.

Each character's first full clear of each supported giant dungeon per CN10
day grants one ordinary extra-entry key. No event variants are generated.
The original clear writer commits task, inventory and clear receipt together.
"""
from dataclasses import dataclass
from pathlib import Path
import json,time,uuid

POLICY='giant-daily-clear-task-20261107-v1'
REWARDS={34310:480356,34360:309244,34730:713224,35110:716829}
def clock():return int(time.time())

@dataclass(frozen=True)
class Task:
    session:object
    run:object
    owner:int
    account:int
    operation:str
    dungeon:int
    graph:str
    epoch:str
    path:Path
    day:int

    def validate(self,db=None):
        s=self.session;r=self.run
        from els_server.domain.dungeon_equipment_loot_flow import current_lease
        if(not current_lease(s)or s.account.uid!=self.owner or s.account.account_id!=self.account
            or s.dungeon_run is not r or r.run_id!=self.epoch or r.identity!=self.dungeon
            or r.graph['source_sha256']!=self.graph or s.reward_run_id!=self.operation
            or Path(s.account.reward_store.path).resolve()!=self.path or s.phase!='dungeon_active'
            or not s.dungeon_substage_synced or not s.part_end_notified or s.dungeon_failed
            or s.active_challenge is not None or r.next is None or r.next['kind']!=4):
            raise ValueError('Giant daily task original full clear changed')
        if db is not None:
            from els_server.storage.item_actor import require_active_character
            if not db.in_transaction or Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()!=self.path:raise ValueError('Giant daily task original writer')
            require_active_character(db,self.owner)
            if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(self.owner,)).fetchone()!=(self.account,):raise ValueError('Giant daily task owner')
        return True

    def identity(self):
        self.validate()
        return dict(policy=POLICY,owner=self.owner,run=self.operation,dungeon=self.dungeon,graph_sha256=self.graph)

def prepare(s):
    r=s.dungeon_run
    if r is None or r.identity not in REWARDS:return None
    original=getattr(s,'_giant_task_actor',s);r=original.dungeon_run
    from els_server.storage.aurora_admissions import day_at
    day=s._giant_task_day if hasattr(s,'_giant_task_actor')else day_at(clock())
    return Task(original,r,original.account.uid,original.account.account_id,original.reward_run_id,
        r.identity,r.graph['source_sha256'],r.run_id,Path(original.account.reward_store.path).resolve(),
        day)

def grant(db,task,owner,run,dungeon_clear):
    if type(task)is not Task or task.owner!=owner or task.operation!=run or dungeon_clear[0]!=task.dungeon:raise ValueError('Giant daily task clear identity')
    task.validate(db)
    day=task.day
    db.execute('''CREATE TABLE IF NOT EXISTS giant_daily_task_rewards(
      owner INTEGER NOT NULL,dungeon INTEGER NOT NULL,day INTEGER NOT NULL,
      run TEXT NOT NULL UNIQUE,operation TEXT NOT NULL UNIQUE,template INTEGER NOT NULL,
      PRIMARY KEY(owner,dungeon,day))''')
    if db.execute('SELECT 1 FROM giant_daily_task_rewards WHERE owner=?AND dungeon=?AND day=?',(owner,task.dungeon,day)).fetchone():return []
    operation=str(uuid.uuid5(uuid.UUID(run),'giant-daily-task'))
    template=REWARDS[task.dungeon]
    db.execute('INSERT INTO giant_daily_task_rewards VALUES(?,?,?,?,?,?)',(owner,task.dungeon,day,run,operation,template))
    from els_server.domain.reward_rules import item_plan
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    plan=[item_plan(template,1)]
    def guard(writer):return writer is db and task.validate(db)
    source=dict(reward_source=POLICY,owner=owner,run=run,dungeon=task.dungeon,
        graph_sha256=task.graph,day=day,template=template)
    cap=_issue_source(db,owner,operation,'phase',source,plan,guard)
    result=grant_items(db,plan,owner,raid_reward_source=cap);task.validate(db)
    return result

def authorize_output(template,authority):
    if authority is None:return False
    from els_server.domain.raid_reward_items import validate_source
    a=validate_source(authority);source=json.loads(a._source)
    if source.get('reward_source')!=POLICY:return False
    if(a.kind!='phase'or source.get('owner')!=a.owner or REWARDS.get(source.get('dungeon'))!=template
        or source.get('template')!=template):raise ValueError('Giant daily task key source')
    a.validate_template(template)
    row=a._db.execute('SELECT owner,dungeon,day,run,template FROM giant_daily_task_rewards WHERE operation=?',(a.operation,)).fetchone()
    if row!=(a.owner,source['dungeon'],source['day'],source['run'],template):raise ValueError('Giant daily task ledger changed')
    return True

def notice(template):
    from els_server.game_data import client_data
    from els_server.protocol.gm_messages import scrolling_notice
    return scrolling_notice('每日巨型本任务完成：已获得'+client_data().item(template)['name']+' ×1。')
