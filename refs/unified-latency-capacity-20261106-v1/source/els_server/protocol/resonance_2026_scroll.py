"""Original DC0710 request: category u8 followed by selected page u8."""
def scroll_request(payload):
    if type(payload) is not bytes or len(payload)!=2:
        raise ValueError('Category scroll request requires two original bytes')
    category,page=payload
    if category not in (0,1,2) or not 1<=page<=4:
        raise ValueError('Category scroll category or page outside original range')
    return category,page
