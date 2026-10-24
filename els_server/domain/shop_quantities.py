"""Local ED pack sizes carried by the native per-template product vector."""
SIZES=(1,10,50,100)
SKU_BASE=1500000000
MAX_DELIVERY=100


def batchable(offer):
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
    from els_server.domain.fashion_bundles import by_template
    from els_server.domain.bag_capacity import PRODUCT_GROUPS
    from els_server.domain.bank_memberships import PRODUCTS
    from els_server.domain.skill_expansion import ORDINARY_PRODUCT
    t=offer['template']
    return (TEMPLATE_MAX_STACKS.get(t,1)>1 and t not in by_template()
            and t not in PRODUCT_GROUPS and t not in PRODUCTS and t!=ORDINARY_PRODUCT)


def variants(offers):
    """Stable SKUs, same template/category; retain every old single-unit SKU."""
    result=[]
    for p in offers:
        result.append(dict(p))
        if p['quantity']!=1:continue
        if not batchable(p):continue
        for index,size in enumerate(SIZES[1:],1):
            sku=SKU_BASE+4*p['template']+index
            price=p['price']*size
            if not 0<sku<2**31 or not 0<=price<2**31:raise ValueError('Native shop pack bounds')
            result.append(dict(p,sku=sku,quantity=size,price=price))
    if len({p['sku'] for p in result})!=len(result):raise ValueError('Shop pack SKU collision')
    return tuple(result)


def delivery_plan(rows,offers,products):
    """Shop-only bound and split; keep the shared grant and stack limits intact."""
    from els_server.domain.inventory_items import LOCAL_MAX_STACK
    from els_server.domain.shop_local_offers import BULK_PACKS
    batch={offers[sku]['template'] for sku,n in products if batchable(offers[sku])}
    total=sum(p['quantity'] for p in rows)
    ordinary=sum(p['quantity'] for p in rows if p['template'] not in batch)
    limit=MAX_DELIVERY
    if batch and rows and all(p['template'] in BULK_PACKS for p in rows):
        limit=BULK_PACKS[rows[0]['template']]
    if ordinary>36 or total>(limit if batch else 36):
        raise ValueError('Expanded shop delivery quantity limit')
    plan=[]
    for p in rows:
        count=p['quantity']
        while count:
            size=min(count,LOCAL_MAX_STACK)
            plan.append(dict(p,quantity=size));count-=size
    if len(plan)>36:raise ValueError('Shop delivery plan bound')
    return plan
