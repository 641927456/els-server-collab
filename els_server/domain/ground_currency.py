"""Ground ED appearance; the issued ledger still owns the exact amount.

Display bands reuse KDropTable::GetEDItemID's witnessed historical boundaries.
Current IDs are verified independently in the current catalog and 1AB6160.
This is a documented local appearance rule, not an official modern drop rate.
"""

def coin_template(amount):
    if type(amount) is not int or not 1 <= amount <= 2**31-1:
        raise ValueError('Ground ED display amount')
    if amount >= 2000:return 127041
    if amount > 150:return 127020
    if amount > 50:return 127010
    return 127000
