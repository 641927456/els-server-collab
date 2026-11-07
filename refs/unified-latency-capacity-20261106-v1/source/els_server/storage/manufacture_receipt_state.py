"""Read-only current inventory refresh for an already authenticated craft receipt."""
import json

def replay_refresh(positions,audit_json,items):
    if not isinstance(positions,list):raise ValueError('Manufacture receipt positions')
    points=set()
    for p in positions:
        if (not isinstance(p,(list,tuple)) or len(p)!=2 or type(p[0]) is not int
                or not 0<=p[0]<=255 or type(p[1]) is not int or not 0<=p[1]<=32767):
            raise ValueError('Manufacture receipt position')
        if tuple(p) in points:raise ValueError('Duplicate manufacture receipt position')
        points.add(tuple(p))
    try:audit=json.loads(audit_json)
    except (TypeError,json.JSONDecodeError) as error:raise ValueError('Manufacture receipt audit') from error
    if not isinstance(audit,dict):raise ValueError('Manufacture receipt audit object')
    legacy='affected_uids' not in audit
    affected=None
    if not legacy:
        uids=audit['affected_uids']
        if (not isinstance(uids,list) or not uids or any(type(uid) is not int or not 0<uid<2**63 for uid in uids)
                or len(set(uids))!=len(uids)):
            raise ValueError('Manufacture receipt affected UIDs')
        affected=set(uids)
    # The 199 acknowledgement has already refreshed historical slots at their
    # CURRENT contents. 105 is a current-state update, not an acquisition delta.
    # A legacy audit identifies templates, not output UIDs: refresh all current
    # owned rows without guessing an output by template or rewriting history.
    changes=[((i['group'],i['slot']),i) for i in items
             if (i['group'],i['slot']) not in points and (legacy or i['uid'] in affected)]
    return changes,legacy
