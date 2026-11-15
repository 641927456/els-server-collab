"""Read current owned pet-fight entrants inside the caller's transaction.

The room/connection owner supplies the transaction and owns queue publication.
This read neither changes pet availability nor grants any battle/task reward.
"""
from dataclasses import dataclass
from els_server.domain.pet_battle import PetInput
from els_server.domain.pet_progression import template
from els_server.protocol.companion_messages import pet_record
from els_server.storage.companion_state import rows
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.pet_expedition import require_available as expedition_available
from els_server.storage.housing_pets import require_available as housing_available


@dataclass(frozen=True)
class Entrant:
    fact:PetInput
    record:bytes


def roster(db,owner,account_id,selection):
    """Freeze three native DTOs and combat facts from a decoded342 selection."""
    require_active_character(db,owner)
    require_owner(db,owner,account_id)
    level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
    if level!=99:raise ValueError('Pet battle requires level99')
    if len(selection)!=3 or len({uid for uid,ability in selection})!=3:
        raise ValueError('Pet battle requires three distinct owned pets')
    owned={p['uid']:p for p in rows(db,owner,'pet')}
    result=[]
    for uid,ability in selection:
        pet=owned.get(uid)
        if pet is None:raise ValueError('Pet battle pet ownership')
        expedition_available(db,owner,uid)
        housing_available(db,owner,uid)
        if 20000<=pet['unit']<=25000 or pet.get('expires_at',0):
            raise ValueError('Pet battle excludes VIP and periodic pets')
        definition=template(pet['unit'])
        if pet['step']!=definition['EVOLUTION_ALL_STEP']:
            raise ValueError('Pet battle requires full pet evolution')
        growth=tuple(pet['personality'].get(str(i),0)for i in range(4))
        if (type(ability)is not int or ability not in(-1,0,1,2,3)
                or any(type(v)is not int or not 0<=v<=1000 for v in growth)):
            raise ValueError('Pet battle growth choice/points')
        if ability!=-1 and not growth[ability]:
            raise ValueError('Pet battle zero points require random growth')
        fact=PetInput(uid,definition['ATTRIBUTE'],ability,growth)
        result.append(Entrant(fact,pet_record(pet)))
    return tuple(result)
