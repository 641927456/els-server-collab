"""Account appearance entitlements and owned item state in one SQLite tx.

Registration survives destruction of its original item, as the CN guide states.
No grants, prices, client stat calculation, timers or new appearance UI.
"""
import hashlib,json,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid


def present(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()is not None


def ensure(db):
    if not db.in_transaction:raise ValueError('Wardrobe schema needs transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_sources (
        item_uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL CHECK(account_id>0),
        template INTEGER NOT NULL CHECK(template>0),registered_owner INTEGER NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS wardrobe_sources_account ON wardrobe_sources(account_id,template)')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_item_state (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE,
        appearance INTEGER NOT NULL CHECK(appearance>=0),hanger INTEGER NOT NULL CHECK(hanger IN (0,1)))''')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_receipts (
        operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,
        account_id INTEGER NOT NULL,kind INTEGER NOT NULL,uids_json TEXT NOT NULL)''')
    # V1 used a global UID primary key. Keep that table as immutable migration
    # history; an ordinary item can legitimately pass through multiple accounts.
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_account_sources (
        account_id INTEGER NOT NULL CHECK(account_id>0),item_uid INTEGER NOT NULL,
        template INTEGER NOT NULL CHECK(template>0),registered_owner INTEGER NOT NULL,
        PRIMARY KEY(account_id,item_uid))''')
    db.execute('CREATE INDEX IF NOT EXISTS wardrobe_account_sources_template ON wardrobe_account_sources(account_id,template)')
    db.execute('CREATE TABLE IF NOT EXISTS wardrobe_schema (version INTEGER PRIMARY KEY)')
    if db.execute('SELECT 1 FROM wardrobe_schema WHERE version=2').fetchone()is None:
        db.execute('INSERT INTO wardrobe_account_sources SELECT account_id,item_uid,template,registered_owner FROM wardrobe_sources')
        db.execute('INSERT INTO wardrobe_schema VALUES(2)')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_favorites (
        account_id INTEGER NOT NULL CHECK(account_id>0),template INTEGER NOT NULL CHECK(template>0),
        PRIMARY KEY(account_id,template))''')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_ticket_sources (
        operation_id TEXT PRIMARY KEY,account_id INTEGER NOT NULL,template INTEGER NOT NULL,
        ticket_uid INTEGER NOT NULL,registered_owner INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_dyes (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE,
        base_json TEXT NOT NULL,appearance_json TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS wardrobe_dye_points (
        account_id INTEGER NOT NULL,palette INTEGER NOT NULL,points INTEGER NOT NULL CHECK(points>=0),
        PRIMARY KEY(account_id,palette))''')


def counts(db,owner,account_id):
    character_uid(owner)
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()!=(account_id,):
        raise ValueError('Wardrobe account owner mismatch')
    if not present(db,'wardrobe_sources'):return {}
    table='wardrobe_account_sources'if present(db,'wardrobe_account_sources')else'wardrobe_sources'
    result=dict(db.execute('SELECT template,COUNT(*) FROM '+table+' WHERE account_id=? GROUP BY template',(account_id,)))
    if present(db,'wardrobe_ticket_sources'):
        for t,n in db.execute('SELECT template,COUNT(*) FROM wardrobe_ticket_sources WHERE account_id=? GROUP BY template',(account_id,)):result[t]=result.get(t,0)+n
    return result


def favorites(db,owner,account_id):
    counts(db,owner,account_id)  # Account ownership guard also applies to reads.
    if not present(db,'wardrobe_favorites'):return []
    result=[r[0]for r in db.execute('SELECT template FROM wardrobe_favorites WHERE account_id=? ORDER BY template',(account_id,))]
    if len(result)>100:raise ValueError('Corrupt wardrobe favorite count')
    return result


def favorite_snapshot(path,owner,account_id):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');return favorites(db,owner,account_id)


def snapshot(path,owner,account_id):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');return counts(db,owner,account_id)


def attach(db,items,owner):
    by_uid={i['uid']:i for i in items}
    if present(db,'wardrobe_item_state'):
        for uid,appearance,hanger in db.execute('SELECT s.item_uid,s.appearance,s.hanger FROM wardrobe_item_state s JOIN inventory_items i ON i.uid=s.item_uid WHERE i.owner=?',(owner,)):
            if hanger not in (0,1):raise ValueError('Corrupt wardrobe hanger')
            by_uid[uid].update(appearance_template=appearance,wardrobe_hanger=bool(hanger))
    if present(db,'wardrobe_dyes'):
        for uid,base,appearance in db.execute('SELECT s.item_uid,s.base_json,s.appearance_json FROM wardrobe_dyes s JOIN inventory_items i ON i.uid=s.item_uid WHERE i.owner=?',(owner,)):
            by_uid[uid].update(dye_colors=json.loads(base),appearance_colors=json.loads(appearance))


def assign(db,owner,item):
    from els_server.domain.wardrobe import validate_state
    validate_state(item)
    if not db.in_transaction or db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],owner)).fetchone()is None:
        raise ValueError('Wardrobe instance owner/transaction')
    ensure(db)
    db.execute('INSERT INTO wardrobe_item_state VALUES(?,?,?) ON CONFLICT(item_uid) DO UPDATE SET appearance=excluded.appearance,hanger=excluded.hanger',
               (item['uid'],item.get('appearance_template',0),int(item.get('wardrobe_hanger',False))))
    assign_colors(db,owner,item)


def assign_colors(db,owner,item):
    from els_server.domain.wardrobe_extensions import color_state
    color_state(item)
    if not db.in_transaction or db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],owner)).fetchone()is None:raise ValueError('Dye owner/transaction')
    ensure(db)
    if not any(item.get('dye_colors',()))and not any(item.get('appearance_colors',())):
        db.execute('DELETE FROM wardrobe_dyes WHERE item_uid=?',(item['uid'],));return
    db.execute('INSERT INTO wardrobe_dyes VALUES(?,?,?) ON CONFLICT(item_uid) DO UPDATE SET base_json=excluded.base_json,appearance_json=excluded.appearance_json',
        (item['uid'],json.dumps(item.get('dye_colors',[0,0,0])),json.dumps(item.get('appearance_colors',[0,0,0]))))


def variants(db,owner,account_id):
    counts(db,owner,account_id)
    if not present(db,'wardrobe_dyes')or not present(db,'wardrobe_account_sources'):return []
    # Destruction and account transfers cease to supply colored hanger variants.
    result=[(uid,t,json.loads(colors))for uid,t,colors in db.execute('''SELECT i.uid,i.template,d.base_json FROM inventory_items i
        JOIN character_owners c ON c.uid=i.owner JOIN wardrobe_account_sources r ON r.item_uid=i.uid AND r.account_id=c.account_id
        JOIN wardrobe_item_state s ON s.item_uid=i.uid AND s.hanger=1 JOIN wardrobe_dyes d ON d.item_uid=i.uid
        WHERE c.account_id=? ORDER BY i.uid''',(account_id,))if any(json.loads(colors))]
    from els_server.domain.inventory_items import validate_item
    for table,query in (
        ('private_bank_items','SELECT b.uid,b.item_json,r.template FROM private_bank_items b JOIN character_owners c ON c.uid=b.owner JOIN wardrobe_account_sources r ON r.item_uid=b.uid AND r.account_id=c.account_id WHERE c.account_id=?'),
        ('shared_bank_items','SELECT b.uid,b.item_json,r.template FROM shared_bank_items b JOIN wardrobe_account_sources r ON r.item_uid=b.uid AND r.account_id=b.account_id WHERE b.account_id=?')):
        if not present(db,table):continue
        for uid,raw,template in db.execute(query,(account_id,)):
            item=validate_item(json.loads(raw))
            if item['uid']!=uid or item['template']!=template or db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(uid,)).fetchone():raise ValueError('Wardrobe bank source identity')
            if item.get('wardrobe_hanger',False)and any(item.get('dye_colors',())):result.append((uid,template,item['dye_colors']))
    if len({u for u,t,c in result})!=len(result):raise ValueError('Duplicate wardrobe source container')
    return sorted(result)


def color_initializations(path,owner,account_id):
    from els_server.protocol.wardrobe_messages import color_notification
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');return [color_notification(1,u,t,c)for u,t,c in variants(db,owner,account_id)]


def change(path,owner,account_id,kind,payload,operation,*,validate=lambda:None):
    from els_server.protocol.wardrobe_messages import register_request,apply_request,favorite_request,acknowledgement
    from els_server.domain.wardrobe import definition,require_owner,validate_state
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    from els_server.domain.ordinary_accessories import definitions as accessories
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_locks import require_unlocked
    if kind in (0x4f4,0x565,0x6d7,0xad6):return extension_change(path,owner,account_id,kind,payload,operation,validate=validate)
    if kind not in (0x4af,0x4b1,0xbee) or not isinstance(operation,str)or not 1<=len(operation)<=160:raise ValueError('Wardrobe operation identity')
    request=register_request(payload)if kind==0x4af else favorite_request(payload)if kind==0xbee else apply_request(payload)
    owner=character_uid(owner);digest=hashlib.sha256(str((owner,account_id,kind)).encode()+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        registry=counts(db,owner,account_id);before=load_items(db,owner);by_uid={i['uid']:i for i in before}
        ensure(db)
        old=db.execute('SELECT request_hash,owner,account_id,kind,uids_json FROM wardrobe_receipts WHERE operation_id=?',(operation,)).fetchone()
        if old:
            if old[:4]!=(digest,owner,account_id,kind):raise ValueError('Conflicting wardrobe retry')
            if kind==0xbee:
                result=acknowledgement(kind,favorite_values=favorites(db,owner,account_id),favorite_mode=request[0]);validate();return result
            changes=[((i['group'],i['slot']),i)for uid in json.loads(old[4])if(i:=by_uid.get(uid))is not None]
            result=acknowledgement(kind,registry,changes);validate();return result
        if kind==0xbee:
            from els_server.domain.wardrobe import catalog
            from els_server.game_data import client_data
            mode,template=request
            if template not in catalog():raise ValueError('Favorite outside native wardrobe catalog')
            client_data().item(template)
            current=favorites(db,owner,account_id)
            if mode==1:
                if template not in current and len(current)>=100:raise ValueError('Wardrobe favorite limit')
                db.execute('INSERT OR IGNORE INTO wardrobe_favorites VALUES(?,?)',(account_id,template))
            else:db.execute('DELETE FROM wardrobe_favorites WHERE account_id=? AND template=?',(account_id,template))
            result=acknowledgement(kind,favorite_values=favorites(db,owner,account_id),favorite_mode=mode)
            db.execute('INSERT INTO wardrobe_receipts VALUES(?,?,?,?,?,?)',(operation,digest,owner,account_id,kind,'[]'))
            validate();return result
        row=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        character=dict(unit_type=row[0],unit_class=row[1]);affected=[]
        targets=[request]if kind==0x4af else [r[2]for r in request]
        for uid in targets:
            item=by_uid.get(uid)
            if item is None or item['group']not in (1,2,7,27,9)or item['count']!=1:raise ValueError('Wardrobe needs owned equipment')
            definition(item['template']);require_owner(item['template'],character)
            if 'expires_at'in item or item.get('sealed',False)or item.get('identified')is False:
                raise ValueError('Timed/sealed/unidentified wardrobe target')
            if kind==0x4af:require_unlocked(item)
        if kind==0x4af:
            item=dict(by_uid[request]);t=item['template']
            existing=db.execute('SELECT template FROM wardrobe_account_sources WHERE account_id=? AND item_uid=?',(account_id,request)).fetchone()
            if existing is not None and existing!=(t,):raise ValueError('Wardrobe source identity conflict')
            if existing is None:db.execute('INSERT INTO wardrobe_account_sources VALUES(?,?,?,?)',(account_id,request,t,owner))
            if t in FASHION_EQUIP_SLOTS or t in accessories():
                item.update(wardrobe_hanger=True,appearance_template=item.get('appearance_template',0));assign(db,owner,item)
            affected=[request]
        else:
            for position,template,uid,colors in request:
                item=dict(by_uid[uid]);base=definition(item['template']);chosen=definition(template)
                require_owner(template,character)
                if position!=base['equip_position']or not registry.get(template):raise ValueError('Unregistered appearance or wrong target position')
                from els_server.domain.normal_equipment import definitions as normal
                if item['template']not in normal()and not item.get('wardrobe_hanger',False):raise ValueError('Target has no registered hanger')
                if any(colors)and not any(t==template and tuple(c)==colors for u,t,c in variants(db,owner,account_id)):raise ValueError('Unregistered account dye variant')
                item['appearance_template']=template;item.setdefault('wardrobe_hanger',False)
                if any(colors)or 'appearance_colors'in item:item['appearance_colors']=list(colors)
                validate_state(item);assign(db,owner,item);affected.append(uid)
        after=load_items(db,owner);current={i['uid']:i for i in after}
        # Only appearance/binding fields can change; identity, location and stats persist.
        strip=lambda i:{k:v for k,v in i.items()if k not in ('appearance_template','wardrobe_hanger','appearance_colors')and not(k=='dye_colors'and not any(v))}
        if [strip(i)for i in after]!=[strip(i)for i in before]:raise ValueError('Wardrobe altered base inventory')
        result=acknowledgement(kind,counts(db,owner,account_id),[((current[u]['group'],current[u]['slot']),current[u])for u in affected])
        db.execute('INSERT INTO wardrobe_receipts VALUES(?,?,?,?,?,?)',(operation,digest,owner,account_id,kind,json.dumps(affected)))
        validate()
        if kind==0x4af and any(current[request].get('dye_colors',())):
            from els_server.protocol.wardrobe_messages import color_notification
            return [result,color_notification(1,request,current[request]['template'],current[request]['dye_colors'])]
        return result


def extension_change(path,owner,account_id,kind,payload,operation,*,validate):
    import secrets
    from els_server.protocol.wardrobe_messages import ticket_request,unregister_request,dye_request,acknowledgement,color_notification
    from els_server.domain.wardrobe import definition,require_owner
    from els_server.domain.wardrobe_extensions import catalog,ticket_selection,unregister_group
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_locks import require_unlocked
    from els_server.domain.item_expiration import require_current
    from els_server.storage.item_instances import remove
    if not isinstance(operation,str)or not 1<=len(operation)<=160:raise ValueError('Wardrobe extension operation')
    request=ticket_request(kind,payload)if kind in (0x4f4,0x565)else unregister_request(payload)if kind==0x6d7 else dye_request(payload)
    owner=character_uid(owner);digest=hashlib.sha256(str((owner,account_id,kind)).encode()+payload).hexdigest();data=catalog()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        registry=counts(db,owner,account_id);ensure(db)
        before=load_items(db,owner);by_uid={i['uid']:i for i in before}
        old=db.execute('SELECT request_hash,owner,account_id,kind,uids_json FROM wardrobe_receipts WHERE operation_id=?',(operation,)).fetchone()
        if old:
            if old[:4]!=(digest,owner,account_id,kind):raise ValueError('Conflicting wardrobe extension retry')
            affected=json.loads(old[4]);events=[acknowledgement(kind,registry,[((i['group'],i['slot']),i)for u in affected if(i:=by_uid.get(u))is not None])]
            if kind==0xad6:
                item=by_uid.get(request[0])
                if item is not None and not any(item.get('dye_colors',())):events.append(color_notification(3,item['uid'],item['template'],[0,0,0]))
                events+=color_initializations_in_db(db,owner,account_id)+[points_notification(db,owner,account_id)]
            validate();return events
        row=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
        character=dict(unit_type=row[0],unit_class=row[1]);changes={};events=[]
        def source(uid):
            item=by_uid.get(uid)
            if item is None or item['group']!=4:raise ValueError('Missing owned wardrobe consumable')
            require_current(item);require_unlocked(item)
            if item.get('sealed',False):raise ValueError('Sealed wardrobe source')
            return item
        def consume(item,n):
            if type(n)is not int or not 1<=n<=item['count']:raise ValueError('Insufficient wardrobe consumable')
            pos=(item['group'],item['slot'])
            if item['count']==n:remove(db,owner,item);changes[item['uid']]=(pos,None)
            else:
                db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(n,item['uid'],owner));changes[item['uid']]=(pos,dict(item,count=item['count']-n))
        def target(uid):
            item=by_uid.get(uid)
            if item is None or item['count']!=1 or item['group']not in (1,2,7,27,9):raise ValueError('Missing owned wardrobe target')
            definition(item['template']);require_owner(item['template'],character);require_unlocked(item)
            if 'expires_at'in item or item.get('sealed',False)or item.get('identified')is False:raise ValueError('Timed/sealed/unidentified wardrobe target')
            return dict(item)
        if kind in (0x4f4,0x565):
            uid,template=request;ticket=source(uid);ticket_selection(ticket['template'],template,character)
            if registry.get(template):raise ValueError('Ticket appearance already registered')
            consume(ticket,1)
            db.execute('INSERT INTO wardrobe_ticket_sources VALUES(?,?,?,?,?)',(operation,account_id,template,uid,owner))
        elif kind==0x6d7:
            scroll_uid,uid=request;scroll=source(scroll_uid);item=target(uid)
            if data['unregister'].get(str(scroll['template']))!=unregister_group(item['template']):raise ValueError('Wrong hanger removal scroll')
            if not item.get('wardrobe_hanger',False):raise ValueError('Target has no hanger')
            if db.execute('DELETE FROM wardrobe_account_sources WHERE account_id=? AND item_uid=? AND template=?',(account_id,uid,item['template'])).rowcount!=1:raise ValueError('Hanger source is not registered to account')
            consume(scroll,1)
            item.update(wardrobe_hanger=False,appearance_template=0);item.pop('appearance_colors',None);assign(db,owner,item)
            changes[uid]=((item['group'],item['slot']),item)
            events.append(color_notification(3,uid,item['template'],[0,0,0]))
        else:
            uid,palette,parts,point_mode,decolor=request;item=target(uid);t=item['template']
            count=data['dye_parts'].get(str(t),0)
            if not count or max(parts)>=count or t in data['dye_held']:raise ValueError('Unsupported dye template/part')
            hair=definition(t)['equip_position']==6
            rule=(data['decolor']if decolor else data['palettes']).get(str(palette))
            if rule is None or rule['hair']!=hair:raise ValueError('Dye palette target category')
            current=list(item.get('dye_colors',[0,0,0]));new=current.copy();n=len(parts)
            balance=db.execute('SELECT points FROM wardrobe_dye_points WHERE account_id=? AND palette=?',(account_id,palette)).fetchone()
            balance=balance[0]if balance else 0
            if decolor:
                if any(parts.values())or not any(current[p]for p in parts):raise ValueError('Invalid decolor request')
                for p in parts:new[p]=0
            elif point_mode:
                if balance<100*n or any(c not in data['groups'][str(rule['group'])]for c in parts.values()):raise ValueError('Insufficient dye points or invalid selected color')
                balance-=100*n
                for p,c in parts.items():new[p]=c
            else:
                if any(parts.values()):raise ValueError('Random dye request specifies a color')
                choices=[c for c in data['groups'][str(rule['group'])]if c!=current[min(parts)]]
                if not choices:raise ValueError('Empty dye distribution')
                color=secrets.choice(choices)
                for p in parts:new[p]=color
            if not point_mode:
                sources=[source(i['uid'])for i in before if i['template']==palette and i['group']==4]
                if sum(i['count']for i in sources)<n:raise ValueError('Insufficient owned dye materials')
                left=n
                for s in sorted(sources,key=lambda i:i['slot']):
                    amount=min(left,s['count'])
                    if amount:consume(s,amount);left-=amount
                from els_server.game_data import client_data
                name=client_data().item(palette)['name']
                if not decolor and not any(x in name for x in ('[科宝]','[阿莉尔]','[路莉尔]')):balance+=n
            if not 0<=balance<2**31:raise ValueError('Dye point bound')
            db.execute('INSERT INTO wardrobe_dye_points VALUES(?,?,?) ON CONFLICT(account_id,palette) DO UPDATE SET points=excluded.points',(account_id,palette,balance))
            item['dye_colors']=new;assign_colors(db,owner,item);changes[uid]=((item['group'],item['slot']),item)
            if item.get('wardrobe_hanger',False)and db.execute('SELECT 1 FROM wardrobe_account_sources WHERE account_id=? AND item_uid=?',(account_id,uid)).fetchone():
                events.append(color_notification(1 if any(new)else 3,uid,t,new))
            events.append(points_notification(db,owner,account_id))
        # Encode all results before commit. Never bill ED or alter base stats.
        result=[acknowledgement(kind,counts(db,owner,account_id),list(changes.values()))]+events
        db.execute('INSERT INTO wardrobe_receipts VALUES(?,?,?,?,?,?)',(operation,digest,owner,account_id,kind,json.dumps(list(changes))))
        validate();return result


def color_initializations_in_db(db,owner,account_id):
    from els_server.protocol.wardrobe_messages import color_notification
    return [color_notification(1,u,t,c)for u,t,c in variants(db,owner,account_id)]


def points_notification(db,owner,account_id):
    import struct
    from els_server.protocol.protocol_codec import Event
    counts(db,owner,account_id)
    points=list(db.execute('SELECT palette,points FROM wardrobe_dye_points WHERE account_id=? ORDER BY palette',(account_id,)))if present(db,'wardrobe_dye_points')else[]
    if len(points)>47 or any(not 0<=v<2**31 for k,v in points):raise ValueError('Dye point snapshot bounds')
    # Native B7C170 dispatch C05 -> BEFE30 -> 2C2D190/2C3F7A0:
    # two maps<int,map<int,int64>>; second map's GAT_DYEING=2 is account points.
    return Event(0x201,kind=0xc05,payload=struct.pack('>IIiI',0,1,2,len(points))+b''.join(struct.pack('>iq',k,v)for k,v in points))


def point_initialization(path,owner,account_id):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');return points_notification(db,owner,account_id)
