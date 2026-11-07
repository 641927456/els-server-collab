"""Apply bank membership inside its caller's atomic shop transaction."""
from els_server.domain.bank_memberships import PRODUCTS
from els_server.storage.bank_state import capacity,set_capacity


def grant(db,owner,template,quantity):
    if not db.in_transaction or template not in PRODUCTS or type(quantity) is not int or quantity!=1:
        raise ValueError('Bank membership quantity or transaction')
    group,before,after=PRODUCTS[template]
    if capacity(db,owner,group)!=before:raise ValueError('Bank membership requires the preceding native tier')
    set_capacity(db,owner,group,after)
