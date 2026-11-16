"""Pure, limited actor requirements reused from actual registered consumers.

These functions do not authorize item use. Caller must separately bind current
actor/session/lease, real offer instance and all SQL-dependent conditions. None
means unknown/unbound, never usable. No consumer or SQL writer is called here.
"""

def _snapshot(character,fields):
    if type(character)is not dict or not set(fields)<=character.keys():return None
    c=dict(character)
    if(type(c.get('unit_class'))is not int or type(c.get('level'))is not int
       or not 1<=c['level']<=99 or type(c.get('transcendence'))is not bool
       or type(c.get('master'))is not bool):return None
    from els_server.domain.character_rules import CLASSES
    if c['unit_class']not in CLASSES:return None
    return c

def skill_book_requirement(template,character):
    """Known book actor predicate only; missing saved seal ownership is unknown."""
    if type(template)is not int:return None
    from els_server.domain.skill_unlocks import catalog,groups,validate_unlock
    rule=catalog()['books'].get(str(template))
    if rule is None:return None
    c=_snapshot(character,('unit_class','level','transcendence','master','skill_seal_groups'))
    if c is None:return None
    try:groups(c)
    except ValueError:return None
    try:validate_unlock(c,rule['seal_group'])
    except ValueError:return False
    return True

def career_item_requirement(template,character):
    """Exact existing transition predicate, calculated on a copy without saving."""
    if type(template)is not int:return None
    from els_server.domain.careers import RULES,transition
    if template not in RULES:return None
    c=_snapshot(character,('unit_type','unit_class','level','transcendence','master','artifact','revision'))
    if c is None or type(c['revision'])is not int or not 0<=c['revision']<2**63:return None
    try:transition(c,template)
    except ValueError:return False
    return True

def cube_branch_evidence(template,character):
    """Only original branch/product qualification; always final_usable=None.

    A matching catalog row alone is not an actor authorization. Root still
    needs the real instance, expiry/lock, current actor, choices, finite grant
    capacity/revision, and special source predicates from the real writer.
    """
    if type(template)is not int:return None
    c=_snapshot(character,('unit_type','unit_class','level','transcendence','master'))
    if c is None or type(c['unit_type'])is not int:return None
    from els_server.domain.growing_adventure_kit import BOX,outputs_for
    if template==BOX:
        try:outputs=outputs_for(c['unit_class'])
        except ValueError:return dict(branch_qualified=False,final_usable=None,kind='growing_kit')
        return dict(branch_qualified=True,final_usable=None,kind='growing_kit',outputs=tuple(dict(x)for x in outputs))
    from els_server.domain.regional_boss_cubes_legacy import BOXES,catalog,pool_for
    if template in BOXES:
        row=catalog().get(template)
        if row is None:return dict(branch_qualified=False,final_usable=None,kind='legacy_regional')
        try:resolved=pool_for(row,c['unit_type'],c['unit_class'])
        except ValueError:return dict(branch_qualified=False,final_usable=None,kind='legacy_regional')
        return dict(branch_qualified=True,final_usable=None,kind='legacy_regional',output_count=len(resolved['entries']))
    return None
