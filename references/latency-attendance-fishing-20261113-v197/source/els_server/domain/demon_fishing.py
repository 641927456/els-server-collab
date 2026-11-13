"""Spirit's Paradise fishing probabilities from Nexon's official disclosure."""
from els_server.domain.npc_exchange_rules import DEMON_FISH, DIANA_TOWN

# https://elsword.nexon.com/News/Probability/View?n4ArticleSN=234
# The catch distribution is conditional on the rod's separate success roll.
# Integer weights retain the published 0.001% rare catch without rounding.
FISH_WEIGHTS = (
    (136203, 1),
    (136204, 14999),
    (136205, 30000),
    (136206, 40000),
    (136207, 15000),
)
from els_server.domain.fishing_equipment import ROD_SUCCESS
REWARD_SOURCE = 'spirit-paradise-fishing'


def require_access(db, owner, account):
    from els_server.domain.town_travel import require_destination
    from els_server.storage.seal_quests import completed_ids, load_character

    character = load_character(db, owner, account, identity_only=True)
    require_destination(DIANA_TOWN, character, completed_ids(db, owner), ())


def authorize_fish(template, authority):
    if authority is None:
        return False
    import json
    from els_server.domain.raid_reward_items import validate_source

    source = validate_source(authority)
    if (template not in DEMON_FISH or source.kind != 'fishing'
            or json.loads(source._source) != dict(reward_source=REWARD_SOURCE, town=DIANA_TOWN)):
        return False
    source.validate_template(template)
    return True
