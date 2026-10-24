"""Pinned native enchant definitions, separate from unimplemented transactions."""
import copy,functools,hashlib,json
from els_server.game_data import DATA_DIR,CLIENT_SHA,client_data

class EnchantData:
    def __init__(self,directory=DATA_DIR):
        raw=(directory/'enchanting.json').read_bytes()
        self.manifest=json.loads((directory/'enchanting.manifest.json').read_text(encoding='utf8'))
        m=self.manifest
        if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=m['sha256']
            or m['source_catalog_sha256']!=client_data().manifest['catalog_sha256']):raise ValueError('Enchant catalog identity')
        data=json.loads(raw)
        for key in ('effects','unresolved_effects','requirements','scrolls','missing_item_templates'):
            if len(data[key])!=m['counts'][key]:raise ValueError('Enchant cardinality')
        self._effects={(r['m_ExtraDamageType'],r.get('bIsForNPC',False)):r for r in data['effects']}
        self._requirements={(r['enchant_type'],r['source_index']):r for r in data['requirements']}
        self._scrolls={r['ID']:r for r in data['scrolls']}
        if (len(self._effects)!=len(data['effects']) or len(self._requirements)!=len(data['requirements'])
            or len(self._scrolls)!=len(data['scrolls'])):raise ValueError('Duplicate enchant identity')
        self._missing=frozenset(data['missing_item_templates'])
        self._cost=data['cost_formula']
        self._attribute_rules=data['attribute_rules']

    def normal_material_cost(self,is_weapon,existing_count,equipment_level,grade):
        """1A080B0's normal cost, with the current empty special-item list."""
        if type(is_weapon) is not bool:raise ValueError('Equipment kind')
        rules=self._attribute_rules
        tiers=rules['weapon_material_tiers'] if is_weapon else rules['armor_material_tiers']
        if type(existing_count) is not int or not 0<=existing_count<len(tiers):raise ValueError('No next material tier')
        if type(equipment_level) is not int or not 1<=equipment_level<=100:raise ValueError('No material level row')
        if type(grade) is not int or str(grade) not in rules['grade_names']:raise ValueError('No material grade row')
        if rules['special_templates']:raise ValueError('Special material policy needs revalidation')
        tier=tiers[existing_count]
        return dict(material_tier=tier,quantity=self.material_quantity(tier,equipment_level,rules['grade_names'][str(grade)]))

    def material_template(self,target):
        if type(target) is not int or str(target) not in self._attribute_rules['material_templates']:raise ValueError('Attribute target')
        return self._attribute_rules['material_templates'][str(target)]

    def elements_compatible(self,slots,target):
        """Native 1A083C0 mutual exclusion only; not full item eligibility."""
        self.material_template(target)
        if len(slots)!=4 or any(type(v) is not int or not 0<=v<=6 for v in slots):raise ValueError('Four element types in 0..6 required')
        elements=set(slots)|{target}
        return all(len(elements&set(group))<=1 for group in self._attribute_rules['exclusive_groups'])

    def normal_ed_cost(self,existing_count,is_weapon,equipment_level,grade):
        """Original base fee only; eligibility and event fee waiver are separate."""
        if type(existing_count) is not int or not 0<=existing_count<5:raise ValueError('Enchant count')
        if type(is_weapon) is not bool:raise ValueError('Equipment kind')
        if type(equipment_level) is not int or not 0<=equipment_level<=255:raise ValueError('Equipment level')
        if type(grade) is not int or str(grade) not in self._cost['grade_addends']:raise ValueError('Equipment grade')
        c=self._cost
        # The supported byte-level inputs yield integral values below float32's
        # exact integer range, including the native float-to-int truncation.
        fee=(equipment_level+c['grade_addends'][str(grade)])*c['scale']*c['count_multipliers'][existing_count]
        return fee if is_weapon else fee//c['armor_divisor']

    def effect(self,effect_id,*,npc=False):
        if type(effect_id) is not int or type(npc) is not bool:raise ValueError('Effect identity')
        try:return copy.deepcopy(self._effects[effect_id,npc])
        except KeyError:raise ValueError('No exact enchant effect variant') from None

    def material_quantity(self,enchant_type,source_index,grade):
        if type(enchant_type) is not int or type(source_index) is not int:raise ValueError('Requirement identity')
        if grade not in ('LOW','NORMAL','RARE','ELITE','UNIQUE','LEGEND'):raise ValueError('Unknown item grade')
        try:return self._requirements[enchant_type,source_index]['quantities'][grade]
        except KeyError:raise ValueError('No exact enchant requirement row') from None

    def scroll(self,item_id):
        if type(item_id) is not int:raise ValueError('Scroll identity')
        try:row=copy.deepcopy(self._scrolls[item_id])
        except KeyError:raise ValueError('Unknown enchant scroll') from None
        return dict(definition=row,item_present=item_id not in self._missing,activation_implemented=item_id in (130149,130150,130151,130152))

@functools.lru_cache(maxsize=1)
def enchant_data():return EnchantData()
