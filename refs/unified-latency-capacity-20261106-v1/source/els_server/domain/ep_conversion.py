"""CN official-guide conversion units; retail catalogue remains separate."""
from dataclasses import dataclass
from els_server.domain.ep_points import MAX_EP


@dataclass(frozen=True)
class Rate:
    ed_per_bundle: int
    ep_per_bundle: int
    source_sha256: str

    def __post_init__(self):
        if type(self.ed_per_bundle) is not int or not 1 <= self.ed_per_bundle < 2**63:
            raise ValueError('Invalid ED conversion unit')
        if type(self.ep_per_bundle) is not int or not 1 <= self.ep_per_bundle <= MAX_EP:
            raise ValueError('Invalid EP conversion unit')
        if (type(self.source_sha256) is not str or len(self.source_sha256) != 64
                or any(c not in '0123456789abcdef' for c in self.source_sha256)):
            raise ValueError('Missing conversion source identity')


def policy():
    # CN official EP guide screenshot, observed2026-10-18:
    # https://els.ztgame.com/game/m_000-1650-00351-787795.shtml
    # EP count1 at100,000ED. This does not admit any retail SKU.
    return Rate(100000, 1, 'c41ce7db8cdd46e5521112f5ba42c382da870bc2f6672838c61f2927b5a7937c')


# Current pinned client result catalogue; local error-to-message policy.
# Exact retail server error responses have not been captured.
from enum import IntEnum

class ConversionResult(IntEnum):
    UNKNOWN=1
    INVALID_STATE=2
    UNKNOWN_CHARACTER=10
    INSUFFICIENT_ED=2656
    EP_LIMIT=2659
    UNAVAILABLE=2661

class ConversionRejected(ValueError):
    def __init__(self,result):
        self.result=int(ConversionResult(result))
        super().__init__('EP conversion rejected: '+str(self.result))
