"""Original1A08330 and862658..862D72; armor eligibility belongs to caller."""
BASE_CODES=(0,1001,1011,1101,1543,1654,1765)
TIERS=(0.,75.,110.,135.)


def _rules():
    result={}
    for first in range(4):
        for second in(0,4,5,6):
            for a in range(4):
                for b in range(4):
                    if (not first and a or not second and b or a+b not in(1,2,3)
                            or first and not a or second and not b):continue
                    code=BASE_CODES[first]*a+BASE_CODES[second]*b;values=[0.]*6
                    if first:values[first-1]=TIERS[a]
                    if second:values[second-1]=TIERS[b]
                    if code in result and result[code]!=tuple(values):raise ValueError('Native armor rule collision')
                    result[code]=tuple(values)
    if len(result)!=45:raise ValueError('Original armor switch coverage differs')
    return result


RULES=_rules()


def classify(attributes):
    if type(attributes)is not tuple or len(attributes)!=4 or any(type(v)is not int or not 0<=v<=6 for v in attributes):
        raise ValueError('Four original0..6 attribute sources required')
    return sum(BASE_CODES[v]for v in attributes)


def values(attributes):
    # Classifier sums first. Preserve its collision behavior even for tuples
    # rejected by inventory admission; do not reinterpret incompatible inputs.
    return RULES.get(classify(attributes),(0.,)*6)
