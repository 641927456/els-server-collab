from contextlib import closing
import sqlite3
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.bag_capacity import expand
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS

def enlarge(path,uid):
    with closing(sqlite3.connect(path))as db,db:
        # An owned post-expansion fixture, using the current capacity model.
        # This does not claim to test a purchase or new acquisition source.
        expand(db,uid,200751,36);expand(db,uid,200751,8)
        items=load_items(db,uid)
        fashion=next(i for i in items if TEMPLATE_BAG_GROUPS[i['template']]==7 and TEMPLATE_MAX_STACKS[i['template']]==1)
        weapon=next(i for i in items if TEMPLATE_BAG_GROUPS[i['template']]==1 and TEMPLATE_MAX_STACKS[i['template']]==1)
        fashion_count=sum(i['group']==7 for i in items)
        weapon_space=388-sum(i['group']==1 for i in items)
        weapon_count=min(381,weapon_space)
        fashion_target=min(800,1191-(len(items)-fashion_count)-weapon_count)
        assert fashion_count<=fashion_target<=840 and weapon_count>0
        if fashion_target>fashion_count:
            grant_items(db,[dict(template=fashion['template'],metadata=fashion['metadata'],group=7,quantity=fashion_target-fashion_count)],uid)
        remaining=1191-len(load_items(db,uid))
        grant_items(db,[dict(template=weapon['template'],metadata=weapon['metadata'],group=1,quantity=remaining)],uid)
        assert len(load_items(db,uid))==1191
