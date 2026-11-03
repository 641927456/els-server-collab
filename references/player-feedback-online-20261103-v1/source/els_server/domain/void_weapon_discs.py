"""Current Type-Void's fifteen native energy discs, separate from Proto."""
TEMPLATES=frozenset((*range(168675,168690),168865))
# Original socket groups are yellow9, red10, blue11. Their giant slot is empty.
DISCS={9:tuple(range(63000011,63000016)),
       10:tuple(range(63000001,63000006)),
       11:tuple(range(63000006,63000011))}

def valid_option(template,group,value):
    return template in TEMPLATES and value in DISCS.get(group,())

def initialize(db,owner,item):
    if item['template'] not in TEMPLATES:return
    from els_server.storage.equipment_options import replace
    before=item.get('option_groups',{})
    updated={**{str(group):list(values) for group,values in DISCS.items()},**before}
    replace(db,owner,item['uid'],before,updated)
    item['option_groups']=updated
