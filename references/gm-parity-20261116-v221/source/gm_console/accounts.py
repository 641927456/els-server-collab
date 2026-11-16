"""Read-only account/role directory. Never instantiate migrating state stores."""
from contextlib import closing
import sqlite3


def directory(config, query='', offset=0, online=(), status='all', sort='newest', limit=30):
    if type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('分页位置无效')
    if status not in ('all','online','offline','disabled','empty') or sort not in ('newest','oldest','name','characters'):
        raise ValueError('账号筛选或排序无效')
    if type(limit) is not int or limit not in (20,30,50,100):raise ValueError('分页大小无效')
    q=str(query).strip().casefold()[:100]
    active={p['uid']:p for p in online}
    if not config.accounts_file.is_file() or not config.state_file.is_file():
        return dict(total=0,accounts=0,characters=0,rows=[],offset=0,limit=limit,
                    counts=dict(all=0,online=0,offline=0,disabled=0,empty=0))
    with closing(sqlite3.connect(config.accounts_file.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        # Only these public management fields leave the account database.
        accounts=db.execute('SELECT id,name,enabled FROM accounts WHERE id>=2 ORDER BY id').fetchall()
    with closing(sqlite3.connect(config.state_file.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.execute('BEGIN')
        roles=db.execute('''SELECT o.account_id,c.uid,c.name,c.unit_type,c.unit_class,c.level,
            COALESCE(b.ed,0),COALESCE(b.experience,0) FROM character_owners o
            JOIN characters c ON c.uid=o.uid LEFT JOIN reward_balances b ON b.uid=c.uid
            WHERE o.account_id>=2 ORDER BY c.uid''').fetchall()
        from els_server.storage.gm_levels import state,version
        versions={}
        for r in roles:
            try:versions[r[1]]=version(*state(db,r[1]))
            except ValueError:versions[r[1]]=None
    by_owner={}
    for owner,uid,name,unit_type,unit_class,level,ed,xp in roles:
        p=active.get(uid)
        from els_server.domain.career_labels import labels
        by_owner.setdefault(owner,[]).append(dict(uid=uid,name=name,unit_type=unit_type,
            **labels(unit_type,unit_class),level_version=versions[uid],
            unit_class=unit_class,level=level,ed=ed,experience=xp,online=p is not None,
            phase=p['phase'] if p else None,session=p['session'] if p else None))
    result=[]
    for identity,name,enabled in accounts:
        children=by_owner.get(identity,[])
        haystack=' '.join([str(identity),name,*[str(c['uid'])+' '+c['name'] for c in children]]).casefold()
        numeric=q.removeprefix('#')
        if numeric.isdecimal():
            if int(numeric)!=identity and not any(int(numeric)==c['uid'] for c in children):continue
        elif q and not all(token in haystack for token in q.split()):continue
        result.append(dict(id=identity,name=name,enabled=bool(enabled),characters=children,
            online_count=sum(c['online'] for c in children)))
    predicates=dict(all=lambda a:True,online=lambda a:bool(a['online_count']),
                    offline=lambda a:a['enabled'] and not a['online_count'],
                    disabled=lambda a:not a['enabled'],empty=lambda a:not a['characters'])
    counts={key:sum(test(row) for row in result) for key,test in predicates.items()}
    result=[row for row in result if predicates[status](row)]
    if sort=='newest':result.sort(key=lambda a:-a['id'])
    elif sort=='oldest':result.sort(key=lambda a:a['id'])
    elif sort=='name':result.sort(key=lambda a:(a['name'].casefold(),a['id']))
    else:result.sort(key=lambda a:(-len(a['characters']),-a['id']))
    offset=min(offset,max(0,(len(result)-1)//limit*limit))
    return dict(total=len(result),accounts=len(accounts),characters=sum(len(by_owner.get(a[0],[])) for a in accounts),
        rows=result[offset:offset+limit],offset=offset,limit=limit,counts=counts)


def inventory(config, account_id, uid):
    if any(type(v) is not int for v in (account_id,uid)) or account_id<2 or uid<1001:
        raise ValueError('账号或角色编号无效')
    if not config.state_file.is_file() or not config.accounts_file.is_file():raise ValueError('存档尚未建立')
    with closing(sqlite3.connect(config.accounts_file.as_uri()+'?mode=ro',uri=True)) as db:
        if not db.execute('SELECT 1 FROM accounts WHERE id=?',(account_id,)).fetchone():raise ValueError('账号不存在')
    with closing(sqlite3.connect(config.state_file.as_uri()+'?mode=ro',uri=True)) as db:
        owner=db.execute('SELECT c.name FROM character_owners o JOIN characters c ON c.uid=o.uid WHERE o.account_id=? AND c.uid=?',(account_id,uid)).fetchone()
        if owner is None:raise ValueError('角色不属于该账号')
        rows=db.execute('SELECT uid,template,count,bag_group,slot FROM inventory_items WHERE owner=? ORDER BY bag_group,slot,uid',(uid,)).fetchall()
    return dict(account_id=account_id,uid=uid,name=owner[0],records=rows)
