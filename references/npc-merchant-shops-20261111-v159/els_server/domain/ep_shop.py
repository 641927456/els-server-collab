"""Source-qualified EP inventory offers and the local weekly reset policy."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from functools import lru_cache
import math,time
from els_server.domain.character_rules import CLASSES
from els_server.domain.ep_accessory_boxes import BOXES as ACCESSORY_BOXES, REWARDS as ACCESSORY_REWARDS

CORRECT_ANSWER_GLASSES = 719992
EP_STORE_ONLY = frozenset((*ACCESSORY_BOXES, CORRECT_ANSWER_GLASSES))
EP_BOUND_ACCESSORIES = EP_STORE_ONLY | ACCESSORY_REWARDS


@dataclass(frozen=True)
class Limit:
    scope: str
    maximum: int
    period: str

    def __post_init__(self):
        if self.scope not in ('account','character'):
            raise ValueError('Unproved EP counter scope')
        if type(self.maximum) is not int or not 1<=self.maximum<2**31:
            raise ValueError('Invalid EP purchase maximum')
        if type(self.period) is not str or not 1<=len(self.period)<=64:
            raise ValueError('Explicit trusted EP period required')


@dataclass(frozen=True)
class Offer:
    template: int
    unit_price: int
    unit_quantity: int
    eligible_classes: frozenset
    limit: Limit | None

    def __post_init__(self):
        if type(self.template) is not int or not 1<=self.template<2**31:
            raise ValueError('Invalid EP product identity')
        if type(self.unit_price) is not int or not 1<=self.unit_price<=10000:
            raise ValueError('Invalid admitted EP price')
        if type(self.unit_quantity) is not int or not 1<=self.unit_quantity<2**31:
            raise ValueError('Explicit EP item quantity required')
        if (type(self.eligible_classes) is not frozenset or not self.eligible_classes
            or any(type(c) is not int or not 1<=c<2**31 for c in self.eligible_classes)):
            raise ValueError('Explicit EP class eligibility required')
        if self.limit is not None and type(self.limit) is not Limit:
            raise ValueError('Invalid trusted EP limit')


# Explicit human server policy, not a retail CN calendar or unlimited claim.
# authorization.json SHA07efaf0d285f0c40292b9989385d90e430dde9c6384ad558423b9ba440d9ffc9
POLICY_VERSION='user-local-EP-20261021-v1'
SHANGHAI=timezone(timedelta(hours=8),'Asia/Shanghai')

def _clock():return time.time()

def weekly_period(now):
    if type(now)not in(int,float)or not math.isfinite(now)or now<0:
        raise ValueError('Invalid trusted EP clock')
    local=datetime.fromtimestamp(now,SHANGHAI)
    reset=(local-timedelta(days=(local.weekday()-2)%7)).replace(hour=10,minute=0,second=0,microsecond=0)
    if local<reset:reset-=timedelta(days=7)
    return POLICY_VERSION+':'+reset.date().isoformat()

def catalog():
    """Resolve the one trusted local period only inside the caller's transaction."""
    period=weekly_period(_clock());classes=frozenset(CLASSES)
    limit=Limit('account',1,period)
    return (Offer(723602,100,1,classes,limit),
            Offer(723603,10,1,classes,limit),
            Offer(723604,5,1,classes,limit),
            Offer(710022,15,100,classes,None))+_pet_offers(classes)+costume_accessory_offers()+special_accessory_offers()


def _pet_offers(classes):
    from els_server.domain.ep_pets import definitions
    return tuple(Offer(row['template'],row['price_ep'],row['quantity'],classes,None)
                 for row in definitions())


@lru_cache(maxsize=1)
def special_accessory_offers():
    classes = frozenset(CLASSES)
    return tuple(Offer(t, price, 1, classes, None) for t, (price, _) in ACCESSORY_BOXES.items())


@lru_cache(maxsize=1)
def costume_accessory_offers():
    from els_server.domain.ep_guardian_necklaces import IDS, definitions
    from els_server.game_data import client_data

    necklaces = definitions()
    classes_by_base = {row['base_class']: frozenset(row['eligible_classes']) for row in necklaces}
    offers = [Offer(row['template'], row['price_ep'], row['quantity'],
                    classes_by_base[row['base_class']], None) for row in necklaces]

    # CN 2025-03-12, section 8. The pinned client stores the permanent eleven
    # parts for each variant in this range, with 118667 marked unused.
    excluded = frozenset((*IDS, 118667))
    data = client_data()
    with data.read_session():
        for template in range(118660, 118837):
            if template in excluded:
                continue
            base_class = data.item(template)['record'][211]
            offers.append(Offer(template, 500, 1, classes_by_base[base_class], None))
    offers.append(Offer(CORRECT_ANSWER_GLASSES, 300, 1, frozenset(CLASSES), None))
    return tuple(offers)
