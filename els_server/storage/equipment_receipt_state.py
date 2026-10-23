"""Current rows for reviewed equipment and inventory-cube receipt kinds."""
import json

def current_changes(db,operation,owner,kind,positions,items):
    # The caller has already matched the authenticated request hash via
    # _previous. Material selection by template is recovered from that exact
    # committed receipt, never from a new search among current stacks.
    if kind not in (0x971,0x5ff,0x21f,0x438,0x43a,0x196,0x6e7,0x9cf,0x555,0x109,0xea,0x567,0x223,0xec,0x663,0x8d1,0x1c0,0x219,0x9ed,0xd4e,0xd50,0xd52,0xd54,0x270,0x272,0xc68):
        raise ValueError('Unreviewed equipment receipt kind')
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,kind):
        raise ValueError('Equipment receipt owner or kind mismatch')
    try:
        before,after=(json.loads(raw) for raw in row[2:])
        if kind in (0x555,0x109):
            before,after=action_history(kind,positions,before,after)
        else:
            if not isinstance(before,list) or not isinstance(after,list) or any(not isinstance(i,dict) for i in before+after):
                raise ValueError('Equipment receipt item arrays')
        points=set(positions)
        affected={i['uid'] for i in before+after if (i['group'],i['slot']) in points}
        if any(type(uid) is not int or not 0<uid<2**63 for uid in affected):
            raise ValueError('Equipment receipt item identity')
    except (TypeError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Equipment receipt history format') from exc
    ordered=list(dict.fromkeys([*positions,*[(i['group'],i['slot']) for i in items if i['uid'] in affected]]))
    current={(i['group'],i['slot']):i for i in items}
    return [(p,current.get(p)) for p in ordered]


def action_history(kind,points,before,after):
    expected=2 if kind==0x555 else 1
    if (not isinstance(before,list) or not isinstance(after,list) or len(before)!=expected or len(after)!=expected
            or not isinstance(points,list) or len(points)!=expected or len(set(points))!=expected
            or any(not isinstance(p,tuple) or len(p)!=2 or type(p[0]) is not int or not 0<=p[0]<=255
                   or type(p[1]) is not int or not 0<=p[1]<=32767 for p in points)):
        raise ValueError('Inventory action receipt shape')
    if not isinstance(before[0],dict):raise ValueError('Inventory action source history')
    if (before[0]['group'],before[0]['slot'])!=points[0]:raise ValueError('Inventory action source position')
    if after[0] is not None:
        if not isinstance(after[0],dict) or after[0]['uid']!=before[0]['uid'] or (after[0]['group'],after[0]['slot'])!=points[0]:
            raise ValueError('Inventory action remaining source identity')
    if kind==0x555:
        if before[1] is not None or not isinstance(after[1],dict) or (after[1]['group'],after[1]['slot'])!=points[1]:
            raise ValueError('Inventory split destination history')
        if (after[1]['uid']==before[0]['uid'])!=(after[0] is None):raise ValueError('Inventory split retained/new UID history')
    return [i for i in before if i is not None],[i for i in after if i is not None]
