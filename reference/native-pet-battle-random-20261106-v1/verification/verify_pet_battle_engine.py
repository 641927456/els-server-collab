"""Approved combat examples and generated legal-match state invariants."""
from pathlib import Path
from dataclasses import asdict
import hashlib,importlib.util,json,random,sys,time,unittest

P=Path(__file__).resolve().parent
file=P/'candidate/els_server/domain/pet_battle.py'
spec=importlib.util.spec_from_file_location('owned_pet_engine',file)
engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)
Action,Kind,PetInput,Match=engine.Action,engine.Kind,engine.PetInput,engine.Match


class Fixed:
    def __init__(self,draws=()):self.draws=iter(draws);self.choices=[];self.calls=0
    def randrange(self,n):
        self.calls+=1
        value=next(self.draws,0)
        assert 0<=value<n
        return value
    def choice(self,values):
        self.choices.append(tuple(values));return values[-1]


def match(*,attributes=(1,1),abilities=(0,0),points=0,rng=None):
    members=[]
    for side in range(2):
        members.append((100+side,tuple(PetInput(1000+side*10+i,attributes[side],abilities[side],(points,)*4)for i in range(3))))
    return Match(members,rng=Fixed()if rng is None else rng)


def plan(*kinds):return tuple(Action(k)for k in kinds)


def submit_pair(m,a,b):
    for s,actions in zip(m.sides,(a,b)):m.submit(s.uid,actions,s.active)
    return m.resolve()


class Combat(unittest.TestCase):
    def test_native_attributes_and_base_damage(self):
        for a,b,damage in ((1,1,20),(1,2,30),(2,3,30),(3,1,30),(2,1,10),(3,2,10),(1,3,10)):
            m=match(attributes=(a,b))
            result=submit_pair(m,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT))
            self.assertEqual(result.steps[0].damage,damage)
            self.assertEqual(m.sides[1].pets[1010].hp,100-3*damage)

    def test_defence_precedes_cheering_and_is_per_game(self):
        m=match(abilities=(0,2),points=1000)
        result=submit_pair(m,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),plan(Kind.DEFEND,Kind.DEFEND,Kind.DEFEND))
        self.assertEqual([s.owner for s in result.steps[::2]],[101]*3)
        self.assertEqual(m.sides[1].pets[1010].hp,70)
        self.assertEqual(m.sides[1].defence_left,0)
        self.assertTrue(m.finish_animation());self.assertFalse(m.finish_animation())
        with self.assertRaises(ValueError):m.submit(101,plan(Kind.DEFEND,Kind.ATTACK,Kind.ATTACK),1010)
        self.assertIsNone(m.sides[1].actions)

    def test_healing_limit_is_per_round_and_capped(self):
        m=match(abilities=(1,0),points=1000)
        with self.assertRaises(ValueError):m.submit(100,plan(Kind.HEAL,Kind.HEAL,Kind.ATTACK),1000)
        self.assertIsNone(m.sides[0].actions)
        m.sides[0].pets[1000].hp=90
        result=submit_pair(m,plan(Kind.HEAL,Kind.ENCHANT,Kind.ENCHANT),plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT))
        heal=next(s for s in result.steps if s.owner==100 and s.kind==Kind.HEAL)
        self.assertEqual(heal.healing,10);self.assertTrue(heal.patience)
        self.assertEqual(m.sides[0].heal_left,0)
        m.finish_animation();self.assertEqual(m.sides[0].heal_left,1)

    def test_enchant_two_own_turns_no_stack_and_switch_clear(self):
        m=match()
        result=submit_pair(m,plan(Kind.ENCHANT,Kind.DEFEND,Kind.ATTACK),plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT))
        self.assertEqual([s.damage for s in result.steps if s.owner==100],[0,0,30])
        self.assertEqual(m.sides[0].pets[1000].enchant,0)
        m.finish_animation()
        submit_pair(m,plan(Kind.ENCHANT,Kind.HEAL,Kind.DEFEND),plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT))
        self.assertEqual(m.sides[0].pets[1000].enchant,0)
        m.finish_animation()
        result=submit_pair(m,(Action(Kind.ENCHANT),Action(Kind.CHANGE,1001),Action(Kind.ATTACK)),plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT))
        self.assertEqual(m.sides[0].active,1001);self.assertEqual(m.sides[0].pets[1000].enchant,0)
        self.assertEqual([s.damage for s in result.steps if s.owner==100][-1],20)
        # Replaying the exact input still matches its submitted active UID,
        # even though executing CHANGE has changed the current active pet.
        self.assertFalse(m.submit(100,(Action(Kind.ENCHANT),Action(Kind.CHANGE,1001),Action(Kind.ATTACK)),1000))

    def test_critical_boost_defence_integer_order(self):
        m=match(attributes=(1,2),abilities=(2,3),points=1000,rng=Fixed((4999,0)))
        m.sides[0].pets[1000].enchant=2
        result=submit_pair(m,plan(Kind.ATTACK,Kind.ENCHANT,Kind.ENCHANT),plan(Kind.DEFEND,Kind.DEFEND,Kind.DEFEND))
        hit=next(s for s in result.steps if s.kind==Kind.ATTACK)
        self.assertEqual(hit.damage,33);self.assertTrue(hit.critical);self.assertFalse(hit.evaded)

    def test_evasion_consumes_attempted_enchant(self):
        m=match(abilities=(2,3),points=1000)
        m.sides[0].pets[1000].enchant=2
        result=submit_pair(m,plan(Kind.ATTACK,Kind.ENCHANT,Kind.ENCHANT),plan(Kind.DEFEND,Kind.DEFEND,Kind.DEFEND))
        hit=next(s for s in result.steps if s.kind==Kind.ATTACK)
        self.assertEqual(hit.damage,0);self.assertTrue(hit.evaded);self.assertFalse(hit.critical)
        self.assertEqual(hit.states[0].pets[0].enchant,0)

    def test_faint_ends_round_before_unperformed_actions(self):
        m=match();m.sides[1].pets[1010].hp=20
        result=submit_pair(m,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),plan(Kind.ATTACK,Kind.DEFEND,Kind.DEFEND))
        self.assertEqual(len(result.steps),1);self.assertEqual(m.sides[1].defence_left,3)
        self.assertIsNone(result.winner);m.finish_animation()
        with self.assertRaises(ValueError):m.submit(101,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),1010)
        m.submit(101,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),1011)
        self.assertEqual(m.sides[1].active,1011)

    def test_final_pet_winner_and_animation_replay(self):
        m=match()
        for p in m.sides[1].pets.values():p.hp=0
        m.sides[1].pets[1010].hp=20
        result=submit_pair(m,plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK),plan(Kind.ATTACK,Kind.ATTACK,Kind.ATTACK))
        self.assertEqual(result.winner,100);self.assertTrue(m.finish_animation())
        self.assertEqual(m.phase,'finished');self.assertFalse(m.finish_animation())

    def test_timeout_uniform_type_then_living_target(self):
        rng=Fixed();m=match(rng=rng)
        first=plan(Kind.ENCHANT,Kind.ENCHANT,Kind.ENCHANT)
        m.submit(100,first,1000);calls=rng.calls
        self.assertFalse(m.submit(100,first,1000));self.assertEqual(rng.calls,calls)
        m.timeout()
        self.assertEqual(set(rng.choices[0]),set(Kind))
        self.assertEqual(rng.choices[1],(1011,1012))
        self.assertEqual(len(rng.choices[0]),5)

    def test_growth_exact_probability_boundaries_and_random_choices(self):
        for points in(0,1,500,1000):
            m=match(points=points,rng=Fixed(range(5000)));p=m.sides[0].pets[1000]
            self.assertEqual(sum(m._proc(p,0)for _ in range(5000)),points)
        for selected in range(4):
            inputs=tuple((100+i,tuple(PetInput(1000+10*i+j,1,-1,(10,20,30,40))for j in range(3)))for i in range(2))
            m=Match(inputs,rng=Fixed((selected,)*6))
            self.assertTrue(all(p.ability==selected and p.points==(10,20,30,40)[selected]for s in m.sides for p in s.pets.values()))

    def test_generated_legal_match_sequences_preserve_invariants(self):
        # Generate complete action sequences rather than mirroring the damage
        # implementation. Check state invariants after every generated step.
        for seed in range(60):
            rng=random.Random(seed);m=match(attributes=(1+seed%3,1+(seed//3)%3),abilities=(seed%4,(seed//4)%4),points=1000,rng=rng)
            previous={s.uid:s.defence_left for s in m.sides}
            original=tuple(tuple(s.pets)for s in m.sides)
            for _ in range(100):
                result=m.timeout()
                self.assertTrue(1<=len(result.steps)<=6)
                for step in result.steps:
                    for state in step.states:
                        self.assertTrue(0<=state.defence_left<=previous[state.uid])
                        previous[state.uid]=state.defence_left
                        self.assertIn(state.heal_left,(0,1))
                        self.assertTrue(all(0<=p.hp<=100 and 0<=p.enchant<=2 for p in state.pets))
                self.assertEqual(tuple(tuple(s.pets)for s in m.sides),original)
                m.finish_animation()
                if m.phase=='finished':
                    loser=next(s for s in m.sides if s.uid!=m.winner)
                    self.assertTrue(all(p.hp==0 for p in loser.pets.values()))
                    break
            else:self.fail('Generated legal match did not finish within test budget')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Combat)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        source_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),native_Game=False,authenticated_TLS=False,
        production_database_access=False,scope='Pure server turn engine; no admission/network/reward closure claim',
        generated_match_seeds=60,approved_math='HP100,20/30/10,defencehalf,enchant/crit1.5,heal30/45; integer damage truncates once after all multipliers')
    out=P/('engine-check-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
    print(json.dumps(dict(report,str_output=str(out))));raise SystemExit(not report['ok'])
