"""Refund points and consume owned reset items in one caller SQLite transaction."""
import hashlib,json,time
from els_server.protocol.resonance_2026_request import ResonanceAllocationRequest
from els_server.protocol.resonance_2026_reply import snapshot_reply
from els_server.protocol.resonance_2026_reset import inventory_reply
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.resonance_2026_profiles import ResonanceProfiles,NEW_PROFILE_POLICY
from els_server.storage.resonance_2026_pages import CharacterResonancePages,ResonancePage
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.reward_state import validate_balances
from els_server.domain.item_expiration import expired
from els_server.domain.item_locks import locked

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def initialize(db):
    if not db.in_transaction:raise ValueError('Caller transaction required')
    db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_reset_receipts(
        character INTEGER NOT NULL,operation TEXT NOT NULL,account INTEGER NOT NULL,
        request_sha256 TEXT NOT NULL,page_sha256 TEXT NOT NULL,page_revision INTEGER NOT NULL,
        positions_json TEXT NOT NULL,consumed_json TEXT NOT NULL,
        PRIMARY KEY(character,operation))''')

class ResetOperations:
    def __init__(self,db,curve,stats,items):
        self.db,self.stats,self.items=db,stats,items
        self.profiles=ResonanceProfiles(db,curve,stats,new_profile_policy=NEW_PROFILE_POLICY)

    def _reply(self,account,character,kind,positions):
        profiles=self.profiles;progress=profiles.accounts._read(account);pages=profiles.pages.read(account,character)
        if progress is None or pages is None:raise ValueError('Lost reset profile')
        event=snapshot_reply(kind=kind,result=0,progress=progress,page_state=pages,original_definition=self.stats,trailing_value=0,inventory_updates=())
        current={(i['group'],i['slot']):i for i in load_items(self.db,character)}
        event=inventory_reply(event,tuple((position,current.get(position)) for position in positions))
        encode_event(event);return event

    def _consume(self,character,kind,quantity):
        if type(quantity) is not int or quantity<=0:raise ValueError('Reset must refund invested points')
        now=int(time.time());order={t:i for i,t in enumerate(self.items.groups[kind])}
        rows=[i for i in load_items(self.db,character) if i['template'] in self.items.allowed[kind]
            and i['group']==4 and not expired(i,now=now) and not locked(i,now=now)]
        rows.sort(key=lambda i:(i.get('expires_at',2**63-1),order[i['template']],i['slot'],i['uid']))
        if sum(i['count'] for i in rows)<quantity:raise ValueError('Insufficient owned current unlocked reset items')
        consumed=[];positions=[]
        for item in rows:
            if not quantity:break
            amount=min(quantity,item['count']);quantity-=amount
            positions.append((item['group'],item['slot']));consumed.append(dict(uid=item['uid'],template=item['template'],quantity=amount))
            if amount==item['count']:remove(self.db,character,item)
            elif self.db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(amount,character,item['uid'])).rowcount!=1:
                raise ValueError('Reset item ownership changed')
        balances=validate_balances(self.db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(character,)).fetchone())
        if balances['revision']>=2**63-1:raise ValueError('Inventory revision overflow')
        self.db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(character,))
        return tuple(sorted(positions)),consumed

    def edit(self,*,account,character,operation,expected_revision,payload,kind):
        if not self.db.in_transaction:raise ValueError('Caller-owned reset transaction required')
        with self.profiles.pages.transaction():
            return self._edit(account=account,character=character,operation=operation,expected_revision=expected_revision,payload=payload,kind=kind)

    def _edit(self,*,account,character,operation,expected_revision,payload,kind):
        if kind!=0x611:raise ValueError('Reset route')
        profiles=self.profiles;pages=profiles.pages;pages.owner(account,character)
        metadata=profiles._metadata(account,character)
        if metadata is None or metadata[1]!=(0,0,0,0,0):raise ValueError('Unknown temporary reset point policy')
        digest=hashlib.sha256(canonical([account,character,kind,payload.hex(),self.items.digest]).encode()).hexdigest()
        previous=self.db.execute('SELECT account,request_sha256,page_sha256,page_revision,positions_json FROM resonance2026_reset_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
        if previous is not None:
            receipt=self.db.execute('SELECT request_sha256,revision FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
            current=pages.read(account,character)
            if previous[:2]!=(account,digest) or receipt!=previous[2:4] or current is None or current.revision<previous[3]:
                raise ValueError('Reset receipt conflicts or lost page state')
            return self._reply(account,character,0x612,tuple(tuple(p) for p in json.loads(previous[4])))
        if self.db.execute('SELECT 1 FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone():
            raise ValueError('Page operation exists without matching reset item receipt')
        used={}
        def change(current,revision):
            if current is None or not current.enabled:raise ValueError('No opened reset profile')
            selected=current.selected();old=dict(selected.points);rules=pages.rules
            request=ResonanceAllocationRequest.decode(payload)
            if request.selected_page!=current.selected_page:raise ValueError('Stale reset page')
            deltas={}
            for tab,values in request.groups:
                for stat,delta in values:
                    definition=rules.stat(stat)
                    if definition.tab!=tab or stat in deltas:raise ValueError('Reset stat grouping')
                    deltas[stat]=delta
            cost=sum(-d for d in deltas.values() if d<0)
            if not cost:raise ValueError('Coin route requires a committed negative delta')
            updated=dict(old)
            for stat,delta in deltas.items():
                value=old.get(stat,0)+delta
                if not 0<=value<=rules.stat(stat).maximum:raise ValueError('Reset beyond invested/max points')
                updated[stat]=value
            remaining=selected.available_points-sum(deltas.values());item_kind='coin';item_count=cost
            checked=rules.add(current=tuple(sorted(updated.items())),additions=(),available_points=remaining,bonus_points=())
            used['positions'],used['consumed']=self._consume(character,item_kind,item_count)
            edited=tuple(ResonancePage(p.page_id,checked.remaining_points,checked.points) if p.page_id==current.selected_page else p for p in current.pages)
            return CharacterResonancePages(revision,current.enabled,current.selected_page,edited)
        final=pages.mutate(account=account,character=character,operation=operation,expected_revision=expected_revision,
            kind='reset-items',inputs=[kind,payload.hex(),self.items.digest],change=change)
        page_sha,revision=self.db.execute('SELECT request_sha256,revision FROM resonance2026_page_receipts WHERE character=? AND operation=?',(character,operation)).fetchone()
        self.db.execute('INSERT INTO resonance2026_reset_receipts VALUES (?,?,?,?,?,?,?,?)',
            (character,operation,account,digest,page_sha,revision,canonical(used['positions']),canonical(used['consumed'])))
        return self._reply(account,character,0x612,used['positions'])
