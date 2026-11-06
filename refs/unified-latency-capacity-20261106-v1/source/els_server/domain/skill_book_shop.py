"""Sell source-verified seal books under the standalone ED shop policy."""
from els_server.domain.skill_unlocks import catalog

# One ordinary, non-event book per supported seal group. Event and timed
# variants stay valid inventory without becoming duplicate shop entries.
BOOKS=(270970,270971,270972,270973,271311,288509,288510,297762,710334,710335,710336)


def offers():
    books=catalog()['books'];result=[]
    for group,template in enumerate(BOOKS,1):
        row=books[str(template)]
        if row['seal_group']!=group:raise ValueError('Shop seal book group mismatch')
        result.append(dict(sku=1200000000+template,template=template,name=row['name'],
                           category=32,price=50,quantity=1))
    # 50 ED is the existing local skill-service price, not a retail price.
    return tuple(result)
