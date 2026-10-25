"""Finite original Mirror clear rewards; undisclosed rates are local policy."""
import hashlib,json
from els_server.domain.silver_mirror_catalog import catalog,T_CIRCUITS

def draw(seed,label,total):
    if type(total)is not int or total<=0:raise ValueError('Silver Mirror draw bound')
    return int.from_bytes(hashlib.sha256((seed+':'+label).encode()).digest(),'big')%total

def rewards(seed,result):
    p=catalog()['local_policy'];items=[];circuit=None
    if result['slot']in(0,1):
        items.append((30870,p['fragment_quantity']))
        if draw(seed,'force-e',10000)<p['force_e_chance_per_10000']:items.append((136174,1))
        if draw(seed,'T-circuit',10000)<p['circuit_chance_per_10000']:
            pool=catalog()['t_circuits'];circuit=pool[draw(seed,'T-template',len(pool))]
    elif result['weekly']:
        items.append((136228,1))
        special=result['dungeon']in(35760,35770)
        chance=p['special_artifact_chance_per_10000']if special else p['artifact_chance_per_10000']
        if draw(seed,'artifact',10000)<chance:
            parts=(168915,168916,168917,168918)if special else(168915,168916,168917)
            items.append((parts[draw(seed,'artifact-part',len(parts))],1))
    # Story has independent native entry and no normal-stage reward authority.
    # Missing story-specific item rewards are explicitly zero local policy.
    return items,circuit

class ClearSource:
    """Caller-local capability bound to the committed original clear in this DB."""
    def __init__(self,db,owner,run_id):
        if not db.in_transaction:raise ValueError('Silver Mirror T source requires transaction')
        from els_server.storage.silver_mirror_state import seed
        row=db.execute('SELECT owner,proof_sha256,result_json FROM silver_mirror_runs WHERE run_id=?',(run_id,)).fetchone()
        if not row or row[0]!=owner or not row[1]:raise ValueError('Silver Mirror T requires accepted owned clear')
        self.db,self.owner,self.run_id=db,owner,run_id
        self.proof_sha256=row[1]
        self._factory_bound=False
        self.seed=seed(db,run_id)
        items,_=rewards(self.seed,json.loads(row[2]))
        from els_server.domain.reward_rules import item_plan
        self.plan=[item_plan(t,n)for t,n in items]
        self.options=None
    def admit_template(self,template):return template in {p['template']for p in self.plan}
    def bind_factory(self,db,owner,plan):
        if self._factory_bound or db is not self.db or owner!=self.owner or not db.in_transaction or plan!=self.plan:raise ValueError('Silver Mirror clear factory identity/plan')
        self._factory_bound=True

class CircuitSource(ClearSource):
    def __init__(self,db,owner,run_id):
        super().__init__(db,owner,run_id)
        row=db.execute('SELECT result_json FROM silver_mirror_runs WHERE run_id=?',(run_id,)).fetchone()
        _,self.template=rewards(self.seed,json.loads(row[0]))
        if self.template not in T_CIRCUITS:raise ValueError('Silver Mirror T not drawn in this run')
        from els_server.domain.equipment_circuit_rules import material
        row=material(self.template);self.options={'1':[row['options'][draw(self.seed,'T-option',len(row['options']))]]}
    def admit_template(self,template):return template==self.template
    def bind_factory(self,db,owner,plan):
        if self._factory_bound or db is not self.db or owner!=self.owner or not db.in_transaction:raise ValueError('Silver Mirror T factory identity')
        if len(plan)!=1 or(plan[0]['template'],plan[0]['quantity'])!=(self.template,1):raise ValueError('Silver Mirror T finite plan')
        old=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='silver_mirror_awards'").fetchone()
        if old and db.execute('SELECT 1 FROM silver_mirror_awards WHERE run_id=?',(self.run_id,)).fetchone():raise ValueError('Silver Mirror T already generated')
        self._factory_bound=True

def validate_source(source):
    if type(source)not in(CircuitSource,ClearSource):raise ValueError('Silver Mirror finite source required')
    return source
