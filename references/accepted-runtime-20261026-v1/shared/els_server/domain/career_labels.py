"""Chinese job labels from the pinned career-change item definitions."""
from functools import lru_cache

UNIT_NAMES = {1:'艾索德',2:'爱莎',3:'蕾娜',4:'雷文',5:'伊芙',6:'澄',7:'艾拉',
              8:'艾丽希斯',9:'艾迪',10:'露／希尔',11:'萝丝',12:'艾因',13:'菈比',14:'诺亚',15:'莉缇娅'}


@lru_cache(maxsize=1)
def names():
    from els_server.domain.careers import RULES
    from els_server.domain.character_rules import CLASSES
    from els_server.game_data import client_data
    data = client_data()
    result = {cls: UNIT_NAMES[data.unit(cls)['unitType']]
              for cls, row in CLASSES.items() if row['stage'] == 0}
    suffix = '转职变更券'
    for template, rule in RULES.items():
        if rule['kind'] != 'class_change':
            continue
        name = data.item(template)['name']
        if name != rule['name'] or not name.endswith(suffix) or not name[:-len(suffix)]:
            raise ValueError('职业名称来源与当前客户端定义不一致')
        cls = rule['target']
        if cls in result or data.unit(cls)['unitType'] != rule['unit_type']:
            raise ValueError('职业名称归属冲突')
        result[cls] = name[:-len(suffix)]
    if set(result) != set(CLASSES):
        raise ValueError('职业名称定义不完整')
    return result


def labels(unit_type, unit_class):
    from els_server.game_data import client_data
    known = names()
    if (type(unit_class) is not int or unit_class not in known
            or type(unit_type) is not int or client_data().unit(unit_class)['unitType'] != unit_type):
        return dict(unit_name=UNIT_NAMES.get(unit_type, '未知角色'), class_name='未知职业 #'+str(unit_class))
    return dict(unit_name=UNIT_NAMES[unit_type], class_name=known[unit_class])
