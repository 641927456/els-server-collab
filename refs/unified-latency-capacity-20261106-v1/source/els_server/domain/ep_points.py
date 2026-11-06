"""Epic Points: independent character balance, native u64 wire, retail cap."""
MAX_EP=10000

def validate(value):
    if type(value) is not int or not 0<=value<=MAX_EP:raise ValueError('Invalid Epic Point balance')
    return value
