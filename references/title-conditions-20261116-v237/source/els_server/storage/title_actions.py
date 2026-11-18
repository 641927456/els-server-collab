"""Title observations inside successful, receipted inventory transactions."""
import time
from els_server.storage import titles,title_counts


def record(db,owner,kind,*,now=None,**facts):
    # Legacy protocol-only stores have no selected character, as in title_clears.
    if not all(titles.exists(db,t) for t in ('characters','character_owners')):return ()
    return title_counts.advance(db,titles.character(db,owner),int(time.time()) if now is None else now,
                                event=dict(kind=kind,**facts))


def food(db,owner,item):
    from els_server.game_data import client_data
    definition=client_data().item(item['template'])
    record(db,owner,'pet_feed',grade=(definition['flags4']>>20)&15)


def inventory(db,owner,kind,positions,before,after):
    if kind not in (0x5ff,0x1c4,0x1c0):return
    from els_server.game_data import client_data
    remaining={i['uid']:i for i in after if i is not None}
    if kind==0x1c4:
        # The original socket writer puts its target first, even when rolling
        # the same option again. Stones have already been consumed at this point.
        target=next(i for i in before if (i['group'],i['slot'])==positions[0])
        spent=sum(max(0,i['count']-remaining.get(i['uid'],{}).get('count',0)) for i in before)
        level=client_data().item(target['template'])['record'][0xd1]
        for _ in range(spent):record(db,owner,'socket',item_level=level)
        return
    for item in before:
        if item is None:continue
        updated=remaining.get(item['uid'])
        if kind==0x5ff:
            if updated is None or updated.get('enhancement',0)<=item.get('enhancement',0):continue
        elif updated is not None:continue
        row=client_data().item(item['template'])
        if row['item_type'] not in (1,2):continue
        if kind==0x5ff:
            record(db,owner,'enhance',item_level=row['record'][0xd1],success=True)
        else:
            record(db,owner,'dismantle',item_level=row['record'][0xd1],quantity=item['count'])
