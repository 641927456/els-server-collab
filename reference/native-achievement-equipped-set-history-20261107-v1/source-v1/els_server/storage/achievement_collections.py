"""Read owned collection counts; never settle pet/mount clocks or move bank items."""
from els_server.storage.bank_state import load as bank_items


def counts(db,account,owner,now,condition_types):
    result={}
    if condition_types&{67,68}:
        from els_server.domain.character_rules import CLASSES
        careers=list(db.execute('SELECT c.unit_class,c.transcendence FROM characters c '
            'JOIN character_owners o ON o.uid=c.uid WHERE o.account_id=?',(account,)))
        if 67 in condition_types:
            result.update({(67,stage):sum(CLASSES[unit_class]['stage']>=stage for unit_class,_ in careers)for stage in(1,2,3)})
        if 68 in condition_types:result[(68,0)]=sum(bool(transcendence)for _,transcendence in careers)
    if condition_types&{37,38}:
        present={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name IN(?,?)",
            ('companions','mount_lifetimes'))}
        if 'companions'in present:
            joins=[];current=[];args=[]
            if 'mount_lifetimes'in present:
                joins.append('LEFT JOIN mount_lifetimes m ON m.uid=p.uid AND m.owner=p.owner')
                current.append("(p.kind!='mount'OR m.expires_at IS NULL OR ?<m.expires_at)");args.append(now)
            # Match the existing collection projection: all registered pet UIDs;
            # the riding-pet vector excludes expired rental mounts.
            sql='SELECT c.uid,c.unit_type,p.kind,COUNT(*)FROM companions p JOIN characters c ON c.uid=p.owner '
            sql+='JOIN character_owners o ON o.uid=c.uid '+' '.join(joins)
            sql+=' WHERE '+(' AND '.join(current)+' AND 'if current else '')+'o.account_id=? GROUP BY c.uid,c.unit_type,p.kind'
            for uid,unit,kind,count in db.execute(sql,[*args,account]):
                key=(37 if kind=='pet'else 38,unit)
                # Each role-specific condition requires one character's owned
                # collection, not the sum of multiple sibling characters.
                result[key]=max(result.get(key,0),count)
    if 39 in condition_types:result[(39,0)]=len(bank_items(db,owner,group=16))
    if 50 in condition_types:
        from els_server.domain.achievement_catalog import catalog
        from els_server.domain.item_expiration import expired
        from els_server.storage.inventory_state import load_items
        equipment={identity:{value for value in condition['parameters']['m_iEquipItemID'].values()if value}
            for identity,definition in catalog().items()for condition in definition['conditions']if condition['type']==50}
        result.update(((50,identity),0)for identity in equipment)
        owners=db.execute('SELECT DISTINCT i.owner FROM inventory_items i JOIN character_owners o ON o.uid=i.owner '
            'WHERE o.account_id=? AND i.bag_group=9',(account,)).fetchall()
        for (character,)in owners:
            worn=[item['template']for item in load_items(db,character)if item['group']==9 and not expired(item,now=now)]
            for identity,templates in equipment.items():
                # Each condition describes simultaneous equipment on one role.
                result[(50,identity)]=max(result[(50,identity)],sum(template in templates for template in worn))
    if 42 in condition_types and db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='title_ownership'").fetchone():
        from els_server.domain.titles import definition
        collected={}
        rows=db.execute("SELECT t.title,t.expires_at,t.scope FROM title_ownership t "
            "LEFT JOIN character_owners o ON t.scope='character'AND o.uid=t.subject "
            "WHERE(t.scope='account'AND t.subject=?)OR o.account_id=?",(account,account))
        for identity,end,scope in rows:
            title=definition(identity)
            if end and now>=end:continue
            if scope!=('account'if title['m_bAccountTitle']else'character'):continue
            collected.setdefault(title['m_eTitleType'],set()).add(identity)
        result.update(((42,region),len(identities))for region,identities in collected.items())
    return result
