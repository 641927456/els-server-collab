/* Native finalizer input adapter. Never owns an Actor, Buff, or effect object. */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef unsigned long long uptr;
extern u8 game_handle[];
extern u8 dungeon_vtable[];
extern u8 time_vtable[];
extern u8 original_slot[];
extern u8 restore_slot[];
extern u8 archenemy_slot[];
extern u8 archenemy_mod_slot[];
extern u8 patrona_mp_slot[];
extern u8 patrona_mp_vtable[];
extern u8 skill_buff_check_slot[];
extern u8 electron_probability_return[];
extern u8 electron_attack_return[];
extern unsigned char valid_game(void *handle);
extern void *resolve_game(void *handle);
extern void *my_actor(void *game);
extern void *main_effect(void *damage_effect);
extern void set_effect_lifetime(void *entity,float seconds);
extern float time_remaining(void *timer);
extern void set_time_remaining(void *timer, const float *seconds);
extern float awakening_remaining(void *actor);
static u32 get32(void *p, uptr offset) { return *(u32 *)((u8 *)p + offset); }
static u64 get64(void *p, uptr offset) { return *(u64 *)((u8 *)p + offset); }
static void *getptr(void *p, uptr offset) { return *(void **)((u8 *)p + offset); }
/* Generated from approved main states; passive/enemy aliases are excluded. */
static int main_template(u32 factor, u32 template_id) {
  switch (factor) {
__MAIN_FACTORS__
  default: return 0;
  }
}
enum PassiveMode { PASSIVE_NONE, PASSIVE_DUNGEON, PASSIVE_PARENT,
                   PASSIVE_AWAKENING, PASSIVE_RED_MOON, PASSIVE_PATRONA,
                   PASSIVE_COMBAT, PASSIVE_THIRD_AWAKENING, PASSIVE_ELECTRON,
                   PASSIVE_GOLDEN_OATH };
static int passive_mode(u32 factor, u32 template_id) {
  switch (factor) {
__PASSIVE_FACTORS__
  default: return PASSIVE_NONE;
  }
}
static void *own_game(void *actor) {
  void *game;
  if (!actor || !valid_game(game_handle)) return 0;
  game=resolve_game(game_handle);
  if (!game || getptr(game,0)!=dungeon_vtable) return 0;
  return my_actor(game)==actor ? game : 0;
}
static int self_source(void *actor,u64 caster,u8 nonplayer) {
  u64 uid;
  if (nonplayer) return 0;
  uid=((u64 (*)(void *))getptr(getptr(actor,0),0x158))(actor);
  return uid && caster==uid;
}
static void *single_timer(void *buff) {
  void *begin=getptr(buff,0x20),*timer;
  if (!begin || (uptr)getptr(buff,0x28)!=(uptr)begin+sizeof(void *)) return 0;
  timer=getptr(begin,0);
  return timer && getptr(timer,0)==time_vtable ? timer : 0;
}

/* Keep the original duration until it actually expires. This positive value
 * represents the extension on the original object and survives its snapshot.
 * 2^-24 is positive for native expiry and below its 2^-23 display threshold. */
static const float extension_time = 0.000000059604644775390625f;

static int parent_matches(u32 child, u32 factor, u32 template_id) {
  switch (child) {
__PASSIVE_PARENTS__
  default: return 0;
  }
}

static int has_parent(void *actor, u32 factor) {
  void **p=(void **)getptr(actor,0x1858),**end=(void **)getptr(actor,0x1860);
  for (;p!=end;p++) {
    void *buff=*p,*timer;
    if (!buff || *((u8 *)buff+0x86) ||
        !parent_matches(factor,get32(buff,0x160),get32(buff,0x50)) ||
        !self_source(actor,get64(buff,0x130),*((u8 *)buff+0x138))) continue;
    timer=single_timer(buff);
    if (timer && !*((u8 *)timer+0x20) && time_remaining(timer)>0.0f) return 1;
  }
  return 0;
}

static int extension_condition(void *actor, u32 factor, int mode) {
  if (mode==PASSIVE_AWAKENING) return awakening_remaining(actor)>0.0f;
  if (mode==PASSIVE_RED_MOON) return awakening_remaining(actor)>0.0f && has_parent(actor,factor);
  if (mode==PASSIVE_COMBAT) {
    void *combat=((void *(*)(void *,u32))getptr(getptr(actor,0),0x368))(actor,0);
    return combat && *((u8 *)combat+0x129)==1;
  }
  if (mode==PASSIVE_THIRD_AWAKENING) {
    /* Grandeur's original 20aae17 branch reads the awakening stage here. */
    u32 stage=(u32)((uptr)actor+0x11650)^get32(actor,0x11658)^get32(actor,0x11660);
    return stage==3 && awakening_remaining(actor)>0.0f;
  }
  if (mode==PASSIVE_GOLDEN_OATH) {
    void *game=own_game(actor);
    u64 partner_uid=get64(actor,0x1c800);
    return game && has_parent(actor,factor) &&
           ((void *(*)(void *,u64))getptr(getptr(game,0),0x150))(game,partner_uid);
  }
  return mode==PASSIVE_PARENT && has_parent(actor,factor);
}

static int has_separate_effect_clock(int mode) {
  return mode==PASSIVE_PATRONA || mode==PASSIVE_ELECTRON;
}

static int passive_owner(void *buff, void *actor) {
  return !*((u8 *)buff+0x86) && own_game(actor) &&
         self_source(actor,get64(buff,0x130),*((u8 *)buff+0x138));
}

int qualifies(void *buff, void *actor) {
  u32 factor,template_id;
  if (!buff || !actor) return 0;
  factor=get32(buff,0x160);template_id=get32(buff,0x50);
  if (!main_template(factor,template_id) && passive_mode(factor,template_id)!=PASSIVE_DUNGEON) return 0;
  if (*((u8 *)buff+0x86) || *((u8 *)buff+0x138)) return 0;
  return own_game(actor) && self_source(actor,get64(buff,0x130),*((u8 *)buff+0x138)) && single_timer(buff);
}
float held_delta(void *buff, void *actor, float delta) {
  u32 factor;
  int mode;
  void *timer;
  float remaining;
  if (!(delta>0.0f) || !buff || !actor) return delta;
  if (qualifies(buff,actor)) return 0.0f;
  factor=get32(buff,0x160);
  mode=passive_mode(factor,get32(buff,0x50));
  if (mode<=PASSIVE_DUNGEON || !passive_owner(buff,actor)) return delta;
  timer=single_timer(buff);
  if (!timer || *((u8 *)timer+0x20) || *((u8 *)timer+0x44)) return delta;
  remaining=time_remaining(timer);
  if (!(remaining>0.0f)) return delta;
  if (!has_separate_effect_clock(mode) && !extension_condition(actor,factor,mode))
    return remaining==extension_time && delta<remaining ? remaining : delta;
  if (remaining>delta && remaining!=extension_time) return delta;
  if (remaining!=extension_time) set_time_remaining(timer,&extension_time);
  return 0.0f;
}
void update_main(void *buff, void *actor, float delta) {
  ((void (*)(void *,void *,float))getptr(original_slot,0))(buff,actor,held_delta(buff,actor,delta));
}

/* Original Actor update calls this behavior before the TIME finalizer.
 * The last ordinary frame still runs its normal MP update. Later frames
 * retain only the four attribute behaviors on the same buff. */
void update_patrona_mp(void *behavior,void *actor,void *buff,float delta) {
  void *timer;
  if (buff && actor && behavior && getptr(behavior,0)==patrona_mp_vtable &&
      passive_mode(get32(buff,0x160),get32(buff,0x50))==PASSIVE_PATRONA &&
      passive_owner(buff,actor) && (timer=single_timer(buff)) &&
      time_remaining(timer)==extension_time) return;
  ((void (*)(void *,void *,void *,float))getptr(patrona_mp_slot,0))(behavior,actor,buff,delta);
}

/* Preserve the native time window of the large-electron-ball probability.
 * Both identified consumers query 25424 at index 0. Other callers retain
 * the original skill/Buff presence, including the normal trigger itself. */
u8 check_skill_buff(void *actor,u32 skill,u32 index,u8 use_pvp) {
  u8 result=((u8 (*)(void *,u32,u32,u8))getptr(skill_buff_check_slot,0))(actor,skill,index,use_pvp);
  void *caller=__builtin_return_address(0);
  void **p,**end;
  if (!result || skill!=25424 || index!=0 ||
      (caller!=electron_probability_return && caller!=electron_attack_return) || !own_game(actor)) return result;
  p=(void **)getptr(actor,0x1858);end=(void **)getptr(actor,0x1860);
  for (;p!=end;p++) {
    void *buff=*p,*timer;
    if (!buff || passive_mode(get32(buff,0x160),get32(buff,0x50))!=PASSIVE_ELECTRON ||
        !passive_owner(buff,actor) || !(timer=single_timer(buff))) continue;
    if (time_remaining(timer)==extension_time) return 0;
  }
  return result;
}
int hold_arm(void *actor) {
  void **p,**end;void *buff;
  if (!own_game(actor)) return 0;
  p=(void **)getptr(actor,0x1858);end=(void **)getptr(actor,0x1860);
  for(;p!=end;p++) {
    buff=*p;
    if (buff && get32(buff,0x160)==321 && get32(buff,0x50)==322 &&
        !*((u8 *)buff+0x86) && self_source(actor,get64(buff,0x130),*((u8 *)buff+0x138)) &&
        single_timer(buff)) return 1;
  }
  return 0;
}
/* These two callbacks exclusively create Archenemy's held spears. Extend only
 * currently held, generation-valid effects after native creation. Native fire
 * resets their lifetime to 0.35s; native clear/destruction is never intercepted.
 * 999999 is the original engine's own LT_INFINITE clock sentinel (38cb0a). */
void extend_archenemy(void *actor) {
  void *game=own_game(actor),*manager,*records,*finish,*slot,*effect,*graph;
  void **p,**end;u32 handle,index;
  if (!game) return;
  manager=getptr(game,0x500);if (!manager) return;
  records=getptr(manager,0x70);finish=getptr(manager,0x78);
  p=(void **)getptr(actor,0x1c8a0);end=(void **)getptr(actor,0x1c8a8);
  for(;p!=end;p++) {
    if (!*p) continue;
    handle=get32(*p,0x18);if (handle==0xffffffffU) continue;
    index=handle&0xffffU;
    if ((uptr)index>=((uptr)finish-(uptr)records)/16) continue;
    slot=(u8 *)records+(uptr)index*16;effect=getptr(slot,0);
    if (!effect || *(unsigned short *)((u8 *)slot+8)!=(unsigned short)(handle>>16) ||
        get32(slot,12)!=0 || !*((u8 *)effect+0x185)) continue;
    graph=main_effect(effect);
    if (graph && get32(graph,0x2d8)==1 && get32(graph,0x29c)==0)
      set_effect_lifetime(graph,999999.0f);
  }
}
void create_archenemy(void *actor) {
  ((void (*)(void *))getptr(archenemy_slot,0))(actor);extend_archenemy(actor);
}
void create_archenemy_mod(void *actor) {
  ((void (*)(void *))getptr(archenemy_mod_slot,0))(actor);extend_archenemy(actor);
}

/* Private snapshot copy; native behavior, stack and owner restoration run. */
u64 restore_main(void *buff,void *snapshot,void *actor) {
  u8 copy[0x78],entry[28];float values[3];
  void *game,*first,*value_begin,*timer;u32 tick,i,factor,template_id;int mode;
  u64 result;
  union {float f;u32 u;} stamp;
  u64 (*original)(void *,void *,void *)=(u64 (*)(void *,void *,void *))getptr(restore_slot,0);
  if (!buff || !snapshot || !actor) return original(buff,snapshot,actor);
  factor=get32(snapshot,0x4e);template_id=get32(buff,0x50);
  mode=passive_mode(factor,template_id);
  if ((!main_template(factor,template_id) && mode==PASSIVE_NONE) ||
      !self_source(actor,get64(snapshot,0x38),*((u8 *)snapshot+0x4d)) ||
      !(timer=single_timer(buff)) || !(game=own_game(actor))) return original(buff,snapshot,actor);
  first=getptr(snapshot,0x18);
  if (!first || (uptr)getptr(snapshot,0x20)!=(uptr)first+28 || get32(first,0)!=1)
    return original(buff,snapshot,actor);
  value_begin=getptr(first,4);
  if (!value_begin || (uptr)getptr(first,12)!=(uptr)value_begin+12)
    return original(buff,snapshot,actor);
  if (mode>PASSIVE_DUNGEON) {
    float saved=*(float *)value_begin;
    result=original(buff,snapshot,actor);
    if ((result&255)==1 && saved>0.0f && !*((u8 *)buff+0x86) &&
        (timer=single_timer(buff)) && !*((u8 *)timer+0x20) &&
        (has_separate_effect_clock(mode) || extension_condition(actor,factor,mode)) &&
        time_remaining(timer)<=0.0f) set_time_remaining(timer,&extension_time);
    return result;
  }
  tick=get32(game,0xd68);stamp.f=(float)tick;
  if ((double)stamp.f<(double)tick) {stamp.u++;}
  if ((double)stamp.f>=4294967296.0) return original(buff,snapshot,actor);
  for(i=0;i<0x78;i++)copy[i]=*((u8 *)snapshot+i);
  for(i=0;i<28;i++)entry[i]=*((u8 *)first+i);
  for(i=0;i<3;i++)values[i]=*((float *)value_begin+i);
  values[1]=stamp.f;
  *(void **)(entry+4)=values;*(void **)(entry+12)=values+3;*(void **)(entry+20)=values+3;
  *(void **)(copy+0x18)=entry;*(void **)(copy+0x20)=entry+28;*(void **)(copy+0x28)=entry+28;
  return original(buff,copy,actor);
}
