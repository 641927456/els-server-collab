"""User-authorized post-purchase current-use eligibility, read-only.

The same original query transaction owns role/skill/artifact/equipped inventory
and offer reads. This does not create acquisition ownership or a use/move plan.
Unsupported consumers return None, which the existing quick selector refuses.
"""
import copy,json
from els_server.domain.inventory_items import validate_item,FASHION_EQUIP_SLOTS
from els_server.domain.normal_equipment import definitions as normal_definitions
from els_server.domain.ordinary_accessories import definitions as accessory_definitions
from els_server.domain.equipment_requirements import catalog as requirements
from els_server.storage.trade_board_state import _authority,read_offers
from els_server.storage.inventory_state import load_items
from els_server.storage.skill_unlocks import owned_character
from els_server.domain.tradeboard_query import read_snapshot
from els_server.domain.tradeboard_consumable_eligibility import ConsumableContext,canonical_app_gate,eligible as consumable_eligible
from els_server.domain.tradeboard_registered_requirements import skill_book_requirement

POLICY='authorized-current-supported-use-after-real-purchase-v1'


def _wear(item,character,inventory):
    from els_server.game_data import client_data
    from els_server.storage.wear_moves import require_wearable
    from els_server.domain.ring_wear import require_compatible
    from els_server.domain import artifact_progression as artifact
    from els_server.domain import tutorial_accessory as tutorial
    from els_server.domain.item_locks import require_unlocked
    t=item['template'];group=9;qualify=require_wearable
    if t in tutorial.TEMPLATES:
        slots=tutorial.wear_slots(t);qualify=tutorial.require_wearable
    elif t in normal_definitions():slots=(requirements()[1][client_data().item(t)['equip_position']],)
    elif t in accessory_definitions():slots=accessory_definitions()[t]['slots']
    elif t in FASHION_EQUIP_SLOTS:slots=(FASHION_EQUIP_SLOTS[t],)
    else:
        slots=artifact.slots(t)
        if not slots:return None
        group=24;qualify=artifact.require_wearable
        try:require_unlocked(item)
        except ValueError:return False
    for slot in slots:
        try:
            moved=validate_item(dict(item,group=group,slot=slot))
            qualify(moved,character)
            # Same final ring exclusion reader as original wear. Replacing
            # this destination removes its previous wearer, not other slots.
            projected=[i for i in inventory if(i['group'],i['slot'])!=(group,slot)]
            require_compatible(moved,(*projected,moved))
        except ValueError:continue
        return True
    return False


class CurrentUse:
    def __init__(self,db,authority,now):
        if type(now)is not int or now<=0 or not db.in_transaction or db.execute('PRAGMA query_only').fetchone()!=(1,):
            raise ValueError('Actual shared readonly query transaction required')
        self.db=db;self.authority=authority;self.now=now
        _authority(db,authority,authority.path,authority.owner,authority.account_id,0xa0c,now)
        self.character=owned_character(db,authority.owner)
        from els_server.game_data import client_data
        if client_data().unit(self.character['unit_class'])['unitType']!=self.character['unit_type']:
            raise ValueError('Actual role class/family mismatch')
        a=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(authority.owner,)).fetchone()
        self.character['artifact']=dict(template=a[0],evolution=a[1],level=a[2],experience=a[3],potentials=json.loads(a[4]))if a else None
        if self.character['unit_type']==10:
            from els_server.storage.luciel_state import state,active_state
            self.character['luciel_style']=state(db,authority.owner)['style']
            self.character['luciel_active_unit']=active_state(db,authority.owner)['active_unit']
        self.inventory=tuple(copy.deepcopy(load_items(db,authority.owner)))
        from els_server.domain.equipment_chip_flow import current_lease
        self.consumable_gate=canonical_app_gate(authority.session,current_lease)

    def __call__(self,row):
        if not self.db.in_transaction or self.db.execute('PRAGMA query_only').fetchone()!=(1,):
            raise ValueError('Use query snapshot ended or became writable')
        _authority(self.db,self.authority,self.authority.path,self.authority.owner,self.authority.account_id,0xa0c,self.now)
        item=validate_item(copy.deepcopy(row['item']))
        from els_server.domain.item_expiration import require_current
        try:require_current(item,now=self.now)
        except ValueError:return False
        # Exact existing user-authorized purchase transformation, private
        # projection only. Source UID, seal_used and every other attribute stay.
        if item.get('sealed',False):
            if item.get('seal_used',0)>99:return False
            item=dict(item,sealed=False,seal_used=item.get('seal_used',0))
        answer=_wear(item,self.character,self.inventory)
        if answer is not None:return answer
        from els_server.domain.skill_unlocks import catalog as books,unsealed_skills,unlock_notice
        if str(item['template'])in books()['books']:
            if item['group']!=4:return False
            answer=skill_book_requirement(item['template'],self.character)
            if answer is not True:return answer
            # Original consumer's exact read-only next-role notice/skill-state
            # preflight; no seal is granted and no inventory is changed.
            try:
                before=unsealed_skills(self.character);group=books()['books'][str(item['template'])]['seal_group']
                next_role=dict(self.character,skill_seal_groups=(*self.character['skill_seal_groups'],group))
                unlock_notice(next_role,before)
                from els_server.storage.skill_unlocks import saved_initialization
                saved_initialization(self.db,next_role)
            except ValueError:return False
            return True
        return consumable_eligible(item,ConsumableContext(app_gate=self.consumable_gate,
            level=self.character['level'],character_available=True,cooldowns=None),now=self.now)


def read_with_eligibility(db,now,authority):
    """Only production binding: actual offers and actor use the same RO snapshot.

    The selected original F town gate means ordinary dungeon-only recovery
    items fail their actual existing app admission. No extra HP/MP rule exists.
    Other complex consumers stay None until their own real gates are bound.
    """
    reader=CurrentUse(db,authority,now)
    return read_snapshot(db,now,read_offers),reader
