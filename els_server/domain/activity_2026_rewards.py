"""Local official-to-item reward configuration explicitly approved by the user."""
from els_server.domain.activity_2026_stack_policy import effective_stack
import hashlib,json,struct
from types import MappingProxyType
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

CATALOG_SHA256='6160498a1c277d9b3d0819edbbce816991f4a7268acd7fc5069f1772060279a9'

class ActivityRewards:
    def __init__(self,raw,*,scope="three"):
        if scope not in ("three","attendance"):raise ValueError("Reviewed reward scope required")
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=CATALOG_SHA256:
            raise ValueError('Reviewed local activity reward catalog required')
        data=json.loads(raw);c=client_data()
        if data['catalog_sha256']!=c.manifest['catalog_sha256'] or len(data['rewards'])!=43:
            raise ValueError('Fixed client reward identity')
        self.digest=CATALOG_SHA256
        self.rewards=MappingProxyType({r['reward_id']:r for r in data['rewards']})
        self.templates=MappingProxyType({r['template']:r for r in data['templates']})
        if set(self.rewards)!={*range(8127,8169),8173}:raise ValueError('Selected reward coverage')
        for t,row in self.templates.items():
            item=c.item(t)
            if item['name']!=row['name'] or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:
                raise ValueError('Reward item definition changed')

        if scope=='attendance':
            rewards={k:v for k,v in self.rewards.items() if k!=8173}
            used={i['template'] for row in rewards.values() for i in row['items']}
            self.rewards=MappingProxyType(rewards)
            self.templates=MappingProxyType({k:v for k,v in self.templates.items() if k in used})

    def register_inventory(self):
        """Explicit startup registration; retain existing valid stack policies."""
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
        for t,row in self.templates.items():
            if t in meta and (meta[t],groups[t])!=(row['metadata'],row['group']):
                raise ValueError('Conflicting activity item type')
        for t,row in self.templates.items():
            if t not in meta:
                meta[t]=row['metadata'];groups[t]=row['group'];stacks[t]=effective_stack(row['max_stack'])

    def plan(self,reward_id):
        if type(reward_id) is not int or reward_id not in self.rewards:raise ValueError('Unknown selected reward')
        return [dict(template=x['template'],metadata=self.templates[x['template']]['metadata'],
                     group=self.templates[x['template']]['group'],quantity=x['quantity']) for x in self.rewards[reward_id]['items']]

    def notice(self,*,existing):
        """Full4B6 snapshot; callers must include their other known reward rows."""
        if type(existing) is not dict:raise TypeError('Explicit existing reward catalog required')
        rows=dict(existing)
        for rid,row in self.rewards.items():
            values=tuple((x['template'],x['quantity'],x['period_hint']) for x in row['items'])
            if rid in rows and tuple(rows[rid])!=values:raise ValueError('Conflicting reward mapping')
            rows[rid]=values
        if len(rows)>16384:raise ValueError('Reward table bound')
        payload=struct.pack('>I',len(rows))
        for rid,items in sorted(rows.items()):
            if type(rid) is not int or not 1<=rid<2**31 or not isinstance(items,(tuple,list)) or not 1<=len(items)<=256:
                raise ValueError('Nonempty reward row required')
            payload+=struct.pack('>iI',rid,len(items))
            for t,n,period in items:
                if any(type(v) is not int for v in (t,n,period)) or not 1<=t<2**31 or not 1<=n<2**31 or not 0<=period<=32767:
                    raise ValueError('Invalid reward item row')
                payload+=struct.pack('>iiH',t,n,period)
        return Event(0x201,kind=0x4b6,payload=payload)
