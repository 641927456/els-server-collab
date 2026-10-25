"""Isolated local ED shop. Debit, item allocation and receipt commit together."""
import hashlib,json,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid,stored_character_type
from els_server.domain.ice_rules import role_pools
from els_server.domain.inventory_items import fashion_catalog,native_ice_catalog,extended_shop_catalog,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.inventory_state import ensure_inventory,grant_items
from els_server.storage.reward_state import validate_balances
from els_server.protocol.shop_messages import ed_purchase_request,ed_purchase_ack


def catalog(unit_type=None):
    # Complete sets and the separately verified standalone selection coexist.
    from els_server.domain.fashion_bundles import offers as bundle_offers
    from els_server.domain.fashion_singles import offers as single_offers
    from els_server.domain.shop_listing import include_extended
    costumes=bundle_offers(unit_type)
    # Native consume/other category; prices and pool weights are local policy.
    ice=tuple({'sku':880000 if p['template']==800000 else 1000000000+p['template'],
               'template':p['template'],'name':p['name'],'category':p['category'],
               'price':p['price'],'quantity':1} for p in native_ice_catalog()['offers']
               if unit_type is None or p['template'] in role_pools(unit_type))
    extended=tuple(dict(sku=1200000000+p['template'],**{k:p[k] for k in ('template','name','category','price','quantity')}) for p in extended_shop_catalog()['offers'] if include_extended(p))
    from els_server.domain.skill_expansion import ORDINARY_PRODUCT,ORDINARY_SKU
    from els_server.game_data import client_data
    item=client_data().item(ORDINARY_PRODUCT)
    if item['item_type']!=7:raise ValueError('Skill expansion definition mismatch')
    expansion=({'sku':ORDINARY_SKU,'template':ORDINARY_PRODUCT,'name':'技能栏扩张券','category':41,'price':50,'quantity':1},)
    from els_server.domain.acquisition_policy import can_acquire
    from els_server.domain.shop_additions import offers as additional_offers
    from els_server.domain.shop_listing import ice_equipment
    from els_server.domain.pet_support import offers as pet_support_offers
    from els_server.domain.bank_memberships import offers as bank_offers
    from els_server.domain.skill_book_shop import offers as skill_book_offers
    from els_server.domain.bag_capacity import additional_offers as bag_offers
    from els_server.domain.skill_page_shop import offer as skill_page_offer
    from els_server.domain.palette_shop import offers as palette_offers
    result=tuple(p for p in palette_offers()+costumes+single_offers(unit_type)+ice+extended+expansion+additional_offers(unit_type)+pet_support_offers()+bank_offers()+bag_offers()+skill_book_offers()+(skill_page_offer(),)
                 if can_acquire(p['template']) and p['template'] not in ice_equipment())
    if len({p['sku'] for p in result})!=len(result) or len({p['template'] for p in result})!=len(result):raise ValueError('Duplicate shop offer')
    return result


def home_lists(unit_type=1):
    """Current local offers for native home controllers (new, hot, good).

    Include the expanded category families in local featured placement.
    This placement and ED pricing are local policy, not retail campaigns.
    """
    usable=list(role_pools(unit_type))
    from els_server.domain.fashion_singles import offers as single_offers
    fashion=[p['template'] for p in single_offers(unit_type)]
    featured=[]
    for family in (2,4,5,6,9):
        # Keep a compact home list; full category lists retain every offer.
        featured.extend([p['template'] for p in extended_shop_catalog()['offers']
                         if p['category']//10==family and bytes.fromhex(p['record_hex'])[210] in (0,unit_type)][:3])
    offered={p['template'] for p in catalog(unit_type)}
    from els_server.domain.fashion_bundles import offers as bundle_offers
    return tuple([t for t in dict.fromkeys(group) if t in offered] for group in
                 (fashion[:18]+usable[:6],fashion[:6]+usable[:6]+featured,
                  fashion[:12]+[p['template'] for p in bundle_offers(unit_type)][:12]))


def quantity_catalog(unit_type=None):
    from els_server.domain.shop_quantities import variants
    from els_server.domain.careers import RULES as CAREER_RULES
    # Career tickets are immediate services and can only be bought singly.
    return tuple(p for p in variants(catalog(unit_type))
                 if p['template'] not in CAREER_RULES or p['quantity']==1)


def purchase(path,payload,operation_id,uid=1001,*,prepare_career=None,prepare_skill_books=None,prepare_palette=None):
    from els_server.domain.bag_capacity import PRODUCT_GROUPS
    from els_server.storage.bag_capacity import expand
    from els_server.domain.bank_memberships import PRODUCTS as BANK_PRODUCTS
    from els_server.storage.bank_memberships import grant as grant_bank_membership
    uid=character_uid(uid)
    if uid!=1001:operation_id=f"{uid}:{operation_id}"
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:
        raise ValueError('Invalid shop operation identity')
    products=ed_purchase_request(payload)
    from els_server.domain.palette_shop import guarded_request
    palette=guarded_request(payload)
    if palette and not callable(prepare_palette):raise ValueError('Current palette actor callback required')
    if not palette and prepare_palette is not None:raise ValueError('Unexpected palette actor callback')
    from els_server.domain.skill_page_shop import SKU as skill_page_sku
    if any(sku==skill_page_sku for sku,n in products):
        raise ValueError('Instant skill page service requires current session authority')
    from els_server.domain.shop_quantities import batchable,delivery_plan,MAX_DELIVERY
    offers={p['sku']:p for p in quantity_catalog()}
    if any(sku not in offers for sku,_ in products):
        raise ValueError('Unknown local shop SKU')
    from els_server.domain.careers import RULES as CAREER_RULES
    from els_server.domain.skill_book_shop import BOOKS
    career_products=[(offers[sku]['template'],n*offers[sku]['quantity']) for sku,n in products if offers[sku]['template'] in CAREER_RULES]
    if career_products and (len(products)!=1 or career_products[0][1]!=1):
        raise ValueError('Buy one career service at a time')
    book_products=[offers[sku]['template'] for sku,n in products if offers[sku]['template'] in BOOKS]
    if any(n*offers[sku]['quantity']!=1 for sku,n in products if offers[sku]['template'] in BOOKS):
        raise ValueError('Buy one skill book of each grade')
    bank_groups=[BANK_PRODUCTS[offers[sku]['template']][0] for sku,n in products if offers[sku]['template'] in BANK_PRODUCTS]
    if len(bank_groups)!=len(set(bank_groups)):raise ValueError('Only one membership per bank in a purchase')
    # Only stackable inventory products opt into the shop's 100-unit bound.
    bulk=any(batchable(offers[sku]) for sku,n in products)
    if (sum(n for _,n in products)>(MAX_DELIVERY if bulk else 36)
        or sum(n for sku,n in products if not batchable(offers[sku]))>36):
        raise ValueError('Local shop purchase quantity limit')
    cost=sum(offers[sku]['price']*n for sku,n in products)
    digest=hashlib.sha256(payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db:
        def prepared_response(response):
            if palette:
                prepare_palette(db)
                from els_server.protocol.protocol_codec import Event,encode_event
                encode_event(Event(0x201,kind=0x810,payload=response))
            return response
        try:
            db.execute('BEGIN IMMEDIATE')
            if palette:prepare_palette(db)
            ensure_inventory(db)
            db.execute('CREATE TABLE IF NOT EXISTS shop_purchase_receipts (operation_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>=0), response BLOB NOT NULL, items_json TEXT NOT NULL, balances_json TEXT NOT NULL)')
            old=db.execute('SELECT request_sha256,response FROM shop_purchase_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting shop retry')
                if book_products:
                    ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                    if prepare_skill_books is not None:prepare_skill_books(db,None,None,True)
                    response=prepared_response(ed_purchase_ack(0,[],ed).payload)
                    db.commit()
                    return response
                if career_products:
                    # Never apply a transition twice, or re-display an old item
                    # UID/ED balance from purchases predating automatic use.
                    ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                    if prepare_career is not None:prepare_career(db,None,None,True)
                    response=prepared_response(ed_purchase_ack(0,[],ed).payload)
                    db.commit()
                    return response
                # Every inventory product can move, expire or be consumed.
                # Once any saved item or ED changes, an old 810 must not restore
                # historical positions, item state or an earlier ED balance.
                from els_server.storage.inventory_state import load_items
                saved=json.loads(db.execute('SELECT items_json FROM shop_purchase_receipts WHERE operation_id=?',(operation_id,)).fetchone()[0])
                current={i['uid']:i for i in load_items(db,uid)}
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                import struct
                if ed!=struct.unpack_from('>Q',old[1],len(old[1])-8)[0] or any(current.get(i['uid'])!=i for i in saved):
                    response=ed_purchase_ack(0,[],ed).payload
                    response=prepared_response(response)
                    db.commit()
                    return response
                from els_server.domain.skill_expansion import ORDINARY_SKU
                if (any(offers[sku]['template'] in BANK_PRODUCTS for sku,n in products)
                    or all(sku==ORDINARY_SKU or offers[sku]['template'] in PRODUCT_GROUPS for sku,n in products)):
                    # A replay after another purchase must not display an old ED balance.
                    ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                    return prepared_response(ed_purchase_ack(0,[],ed).payload)
                response=prepared_response(old[1])
                db.commit()
                return response
            unit_type=stored_character_type(db,uid)
            allowed={p['sku'] for p in quantity_catalog(unit_type)}
            if any(sku not in allowed for sku,_ in products):raise ValueError('Shop product is not available for this character')
            balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
            if balances['ed']<cost:raise ValueError('Insufficient ED')
            career_state=None
            if career_products:
                from els_server.storage.careers import apply_transition
                career_state=apply_transition(db,uid,career_products[0][0])
            book_state=None
            if book_products:
                from els_server.domain.skill_unlocks import catalog as seal_catalog
                from els_server.storage.skill_unlocks import apply_unlock
                for template in sorted(book_products,key=lambda t:seal_catalog()['books'][str(t)]['seal_group']):
                    character,previous=apply_unlock(db,uid,seal_catalog()['books'][str(template)]['seal_group'])
                    book_state=(character,previous if book_state is None else book_state[1])
            from els_server.domain.skill_expansion import ORDINARY_SKU
            from els_server.storage.skill_expansion import grant_ordinary
            for sku,n in products:
                if sku==ORDINARY_SKU:
                    if n!=1:raise ValueError('Skill expansion quantity must be one')
                    grant_ordinary(db,uid)
                elif offers[sku]['template'] in PRODUCT_GROUPS:
                    expand(db,uid,offers[sku]['template'],n)
                elif offers[sku]['template'] in BANK_PRODUCTS:
                    grant_bank_membership(db,uid,offers[sku]['template'],n)
            from els_server.domain.fashion_bundles import delivery
            plan=[]
            for sku,n in products:
                template=offers[sku]['template']
                if sku==ORDINARY_SKU or template in PRODUCT_GROUPS or template in BANK_PRODUCTS or template in CAREER_RULES or template in BOOKS:continue
                members=delivery(template,n,unit_type)
                if members is None:members=[(template,n*offers[sku]['quantity'])]
                plan.extend({'template':t,'metadata':VERIFIED_TEMPLATES[t],
                             'group':TEMPLATE_BAG_GROUPS[t],'quantity':count} for t,count in members)
            plan=delivery_plan(plan,offers,products)
            items=grant_items(db,plan,uid) if plan else []
            balances['ed']-=cost;balances['revision']+=1
            validate_balances(tuple(balances[k] for k in ('ed','experience','revision')))
            response=ed_purchase_ack(0,items,balances['ed']).payload
            db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',(balances['ed'],balances['revision'],uid))
            if career_state is not None and prepare_career is not None:
                # Encode the career and skill notifications before any debit,
                # state change or receipt can commit.
                prepare_career(db,*career_state,False)
            if book_state is not None and prepare_skill_books is not None:
                prepare_skill_books(db,*book_state,False)
            db.execute('INSERT INTO shop_purchase_receipts VALUES (?,?,?,?,?,?)',(operation_id,digest,cost,response,json.dumps(items,sort_keys=True),json.dumps(balances,sort_keys=True)))
            response=prepared_response(response)
            db.commit()
            return response
        except BaseException:
            db.rollback();raise


def bank_purchase_refresh(path,payload,operation_id,uid,response):
    """Any inventory purchase replay restores current affected slots."""
    from els_server.storage.inventory_state import load_items
    from els_server.storage.inventory_management import _updates
    import struct
    ed_purchase_request(payload)
    if struct.unpack_from('>I',response,8)[0]:return []
    if uid!=1001:operation_id=f'{uid}:{operation_id}'
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN')
        row=db.execute('SELECT items_json FROM shop_purchase_receipts WHERE operation_id=?',(operation_id,)).fetchone()
        if row is None:raise ValueError('Missing committed bank purchase receipt')
        saved=json.loads(row[0])
        if not saved:return []
        current=load_items(db,uid);by_uid={i['uid']:i for i in current};by_position={(i['group'],i['slot']):i for i in current}
        positions={(i['group'],i['slot']) for i in saved}
        positions.update((by_uid[i['uid']]['group'],by_uid[i['uid']]['slot']) for i in saved if i['uid'] in by_uid)
        return _updates([(p,by_position.get(p)) for p in sorted(positions)])
