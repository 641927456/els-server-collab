"""Finite native circuit records with explicitly versioned compatible generation."""
import functools,hashlib,json,secrets
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

POLICY_SHA='3e6fef87c5e6f355047d24ff770101d037601c515cc67ddde2557fa9398fd3a4'


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/equipment_circuits.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=POLICY_SHA:raise ValueError('Circuit policy identity changed')
    c=json.loads(raw)
    if c['schema_version']!=1 or c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:
        raise ValueError('Circuit native build mismatch')
    if len(c['materials'])!=72 or len(c['targets'])!=120 or len(c['options'])!=7590:
        raise ValueError('Circuit finite policy coverage')
    for name in ('materials','targets'):
        for key,r in c[name].items():
            d=client_data().item(int(key))
            if (r['template']!=int(key) or d['item_type']!=2 or d['equip_position']!=r['part']
                    or d['metadata']!=r['metadata'] or r['registered_group']!=1 or r['max_stack']!=1
                    or hashlib.sha256(d['record']).hexdigest()!=r['record_sha256']):
                raise ValueError('Circuit finite native record mismatch')
    return c


def material(template):
    row=catalog()['materials'].get(str(template))
    return row if row is not None else derived_materials().get(str(template))
def target(template):return catalog()['targets'].get(str(template))


SHAPES={'I-1':1,'I-2':2,'T-1':3,'T-2':4,'T-3':5,'T-4':6,
        'L-1':7,'L-2':8,'L-3':9,'L-4':10}
COLORS={'演算':1,'循环':2,'复原':3}


@functools.lru_cache(maxsize=1)
def derived_materials():
    """Popular/T-family circuits share the policy shape/color option pool.

    The pinned policy enumerates 72 I/L records; the current client also ships
    the popular-prefix family and T-1..T-4 with the same record layout and the
    same 10-shape x 3-color option table.
    """
    import re
    from els_server.game_data import client_data
    pools={}
    for row in catalog()['options'].values():
        pools.setdefault((row['m_eCircuitItemShapeType'],row['m_eCircuitItemColorType']),[]).append(row['ID'])
    data=client_data()
    with data.connect() as db:
        rows=db.execute("SELECT id,name,equip_position,metadata,item_type FROM items WHERE name LIKE '%型%增幅电路（%'").fetchall()
    result={}
    for template,name,part,metadata,item_type in rows:
        if item_type!=2 or str(template) in catalog()['materials']:continue
        shape=re.search(r'(I-[12]|T-[1-4]|L-[1-4])型',name)
        color=re.search(r'（(演算|循环|复原)）',name)
        if shape is None or color is None:continue
        options=pools.get((SHAPES[shape.group(1)],COLORS[color.group(1)]),[])
        if not options or part not in (8,9,10,11):continue
        result[str(template)]=dict(template=template,part=part,shape=SHAPES[shape.group(1)],
            color=COLORS[color.group(1)],options=options,metadata=metadata,max_stack=1,registered_group=1)
    return result


def validate_material(template,values):
    row=material(template)
    if row is None or not isinstance(values,(list,tuple)) or len(values)!=1 or type(values[0]) is not int or values[0] not in row['options']:
        raise ValueError('Circuit requires one native option in its finite shape/color pool')
    return list(values)


def generate(template,randbelow=secrets.randbelow):
    row=material(template)
    if row is None:raise ValueError('Unsupported circuit material')
    roll=randbelow(len(row['options']))
    if type(roll) is not int or not 0<=roll<len(row['options']):raise ValueError('Circuit generation RNG range')
    return {'1':[row['options'][roll]]}


def root(template):
    row=target(template)
    if row is None:raise ValueError('Unsupported circuit target')
    return catalog()['root_by_part'][str(row['part'])]


def validate_grid(template,values):
    if target(template) is None or not isinstance(values,(list,tuple)) or len(values)!=16:
        raise ValueError('Circuit armor needs sixteen slots')
    if any(type(v) is not int or v!=0 and str(v) not in catalog()['options'] for v in values) or values[root(template)]!=0:
        raise ValueError('Invalid circuit option or reserved root')
    return list(values)


def active_slots(template,values):
    """Native B32630/B32160 pipe traversal. Open circuits have no active effect."""
    values=validate_grid(template,values);c=catalog();start=root(template)
    shapes=[c['options'][str(v)]['m_eCircuitItemShapeType'] if v else 0 for v in values]
    shapes[start]=c['root_shape_by_part'][str(target(template)['part'])]
    visited=[];closed=False
    opposite={1:3,2:4,3:1,4:2};step={1:-4,2:1,3:4,4:-1}
    def visit(pos,incoming=0):
        nonlocal closed
        if not 0<=pos<16 or not shapes[pos]:return False
        ports=list(c['ports'][str(shapes[pos])])
        if incoming:
            if opposite[incoming] not in ports:return False
            ports.remove(opposite[incoming])
        if pos in visited:
            if pos==start:closed=True
            return True
        visited.append(pos)
        for direction in ports:
            row,col=divmod(pos,4)
            if direction==1 and row==0 or direction==2 and col==3 or direction==3 and row==3 or direction==4 and col==0:
                return False
        if len(ports) not in (1,2):return False
        if pos==start:return visit(pos+step[ports[0]],ports[0])
        return all(visit(pos+step[d],d) for d in ports)
    return [p for p in visited if p!=start] if visit(start) and closed else []


def uniform_color(template,values):
    slots=active_slots(template,values)
    colors={catalog()['options'][str(values[p])]['m_eCircuitItemColorType'] for p in slots}
    return next(iter(colors)) if len(colors)==1 else 0
