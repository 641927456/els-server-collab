"""Native CP from the signed support producer; bind it to the current owned inputs.

As with the existing Guild native-CP protocol, the client computes this value.
This is not an independent server-side anti-cheat computation.
"""
import hashlib,json,math,struct,sqlite3,time
from contextlib import closing
from els_server.domain.raid_admission import native_definition

MAGIC=0x52435031


def active_pet(account):
    from els_server.storage.companion_state import rows
    with closing(sqlite3.connect(account.store.path,timeout=10))as db:
        db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():return None
        row=db.execute('SELECT pet FROM companion_active WHERE owner=?',(account.uid,)).fetchone()
        if not row or not row[0]:return None
        pet=next((p for p in rows(db,account.uid,'pet')if p['uid']==row[0]),None)
        if pet is None:raise ValueError('Raid CP active owned pet missing')
        return dict(pet,current=not pet.get('expires_at')or time.time()<pet['expires_at'])


def basis(session):
    account=session.account
    character=account.character();items=account.get_inventory_snapshot()['items']
    from els_server.domain.character_stats import equipment_contributes
    effective=[(i['uid'],equipment_contributes(i,character))for i in items if i['group']==9]
    source=json.dumps([character,items,account.get_skills(),effective,active_pet(account)],sort_keys=True,separators=(',',':')).encode()
    return account,account.uid,session.shop_session_id,hashlib.sha256(source).digest()


def request(session,payload,*,fresh=False):
    if fresh:session._raid_native_power=None
    if len(payload)<16 or payload[-16:-12]!=struct.pack('>I',MAGIC):return payload
    magic,owner,value=struct.unpack('>IQf',payload[-16:])
    if owner!=session.account.uid or not math.isfinite(value) or not 0<=value<=4294967040:
        raise ValueError('Raid native CP source/number')
    from els_server.domain.equipment_chip_flow import current_lease
    if not current_lease(session):raise ValueError('Raid native CP current actor')
    session._raid_native_power=(basis(session),value)
    return payload[:-16]


def allowed(session,identity):
    native=native_definition(identity)
    if native is None:return True
    required=native.get('limitCombatCapability',0)
    if not required:return True
    proof=getattr(session,'_raid_native_power',None)
    return bool(proof is not None and proof[0]==basis(session) and proof[1]*100>=required*95)
