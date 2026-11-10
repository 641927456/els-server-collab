"""Current HousingItemTemplet pet mats and their original integer parameters."""
# HousingItemTemplet.lua SHA6602935cbbef365877401abf27d93b030dfa2869779fcfba16f64864f3413dc7.
# HousingData.lua SetMaxHousingPetMet(1): one pet mat in the saved room.
ROWS=((570234,1,'5419db14990738ca300e99b7f17774cfd8591c215d39de898a840fb181f51bd0'),
      (570286,1,'38fdf561bbe9c883714d7fca7dca9a5b89d5e6f01c92414bb75589ce764c157d'),
      (570405,1,'69c64b40d764e60ea59e61705ea0c33fbdbfff59ef04114242c14c72c8f69764'),
      (570566,1,'580d91e4b9065f0bd5d8ea868c2a539f5042b6d95e6d5073e1ab4dd147046130'),
      (580040,1,'5aaab585bcc6724033dadffd6fbaee95f056dd3bf8ad14bab24e615988a58453'),
      (580119,1,'1f677144434f2ba3657b7bf3f39b8de524c0c875c10380adff6617e96d1f5997'))
MATS={570234:(1,86400),570286:(4,28800),570405:(4,28800),
      570566:(4,28800),580040:(4,28800),580119:(4,28800)}
TEMPLATES=frozenset(MATS)
# Small mat: original Ariel10018 stock, original KIM ED price30000000.
# The other five readers preserve existing ownership; their DIY pools are
# not inferred from the display set or the item's native resale value.
OWNED_ONLY=TEMPLATES-{570234}


def mat(layout):
    """The single pet mat from an already validated unexpanded saved layout."""
    legacy,new,grid,floor,expansion=layout
    rows=[(v[1],v[2])for k,v in legacy if v[2]in TEMPLATES]
    if len(rows)>1:
        raise ValueError('Housing permits one pet mat')
    if not rows:
        return None
    uid,template=rows[0];capacity,period=MATS[template]
    return dict(uid=uid,template=template,capacity=capacity,period=period)
