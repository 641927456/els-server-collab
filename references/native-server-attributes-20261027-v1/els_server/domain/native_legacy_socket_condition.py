"""Original1991230 first qualifying template option for resistance D0.

Socket application quantity is a gate, not the worn-piece threshold. A prior
extraction-only option terminates this lookup. The caller supplies the
independently selected original inventory piece count when a threshold exists.
"""


def requirement(template_options,definitions):
    if type(template_options)is not tuple:
        raise ValueError('Original ordered template options required')
    for identity in template_options:
        if type(identity)is not int or not 0<=identity<2**31:
            raise ValueError('Original nonnegative option ID required')
        definition=definitions.get(identity)
        if definition is None:continue
        count=definition.get('m_iSocketApply',0)
        minimum=definition.get('m_iSocketCondition',0)
        if any(type(value)is not int or not -2**31<=value<2**31 for value in(count,minimum)):
            raise ValueError('Original signed32 socket condition required')
        if count>0:return count,minimum
        if definition.get('m_bSocketExtraction',False):return None
    return None


def enabled(template_options,definitions,*,piece_count):
    if type(piece_count)is not int or not 0<=piece_count<2**31:
        raise ValueError('Original selected inventory piece count required')
    source=requirement(template_options,definitions)
    return source is not None and source[1]<=piece_count
