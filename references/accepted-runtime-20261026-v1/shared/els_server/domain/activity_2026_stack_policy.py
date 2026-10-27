"""Apply the current formal stack policy to late activity registrations.

Source reward catalogues stay immutable. Singleton evidence stays one and
native caps above the local floor remain intact, matching formal inventory.
"""
from els_server.domain.inventory_items import LOCAL_MAX_STACK

def effective_stack(source_cap):
    if type(source_cap) is not int or not 1<=source_cap<2**31:
        raise ValueError('Explicit positive original stack policy required')
    return max(source_cap,LOCAL_MAX_STACK) if source_cap>1 else 1
