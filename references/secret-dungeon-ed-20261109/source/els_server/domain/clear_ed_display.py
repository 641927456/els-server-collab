"""Project committed run ED into native LineItemED; never grant money here."""
import hashlib,json,sqlite3,struct,uuid
from contextlib import closing

def amount(session,clear_ed,*,transaction=None):
    from els_server.domain.drop_pickup import GROUND_ED
    run=session.reward_run_id;owner=session.account.uid
    drops=[drop for drop in session.world_drops.values()if drop.get('pickup_committed')and drop['run_id']==run and drop['owner']==owner and drop['template']in GROUND_ED]
    if not drops:return clear_ed
    def read(db):
        total=clear_ed
        for drop in drops:
            operation=str(uuid.uuid5(uuid.UUID(run),f"pickup:{owner}:{drop['stage']}:{drop['drop_id']}"))
            proof=b'local-world-pickup-v1'+uuid.UUID(run).bytes+struct.pack('>Qiiii',owner,drop['stage'],drop['npc_key'],drop['drop_id'],drop['template'])+bytes.fromhex(drop['death_proof_sha256'])+bytes.fromhex(drop['payload_hex'])
            saved=db.execute('''SELECT r.proof_sha256,r.grant_json,t.owner,t.effect_json
                FROM reward_receipts r JOIN reward_title_receipts t ON t.run_id=r.run_id
                WHERE r.run_id=?''',(operation,)).fetchone()
            if saved is None or saved[0]!=hashlib.sha256(proof).hexdigest()or saved[2]!=owner:raise ValueError('Clear ED requires exact committed owned pickup')
            grant=json.loads(saved[1]);effect=json.loads(saved[3])
            if grant.get('title_economy')!='ground_ed'or grant['ed']!=drop['ed']or effect['owner']!=owner or effect['source']!='ground_ed'or effect['base_ed']!=drop['ed']:raise ValueError('Clear ED pickup receipt source changed')
            total+=effect['ed']
        # LineItemED reads a signed32 result scalar. Refuse an unrepresentable
        # new result before the clear writer commits; never silently truncate.
        if type(total)is not int or not 0<=total<=2**31-1:raise ValueError('Native result ED scalar bound')
        return total
    if transaction is not None:return read(transaction)
    with closing(sqlite3.connect(session.account.reward_store.path,timeout=10))as db:return read(db)
