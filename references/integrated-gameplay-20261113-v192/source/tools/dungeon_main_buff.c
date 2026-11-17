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
extern unsigned char valid_game(void *handle);
extern void *resolve_game(void *handle);
extern void *my_actor(void *game);
extern void *main_effect(void *damage_effect);
extern void set_effect_lifetime(void *entity,float seconds);
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
static int single_timer(void *buff) {
  void *begin=getptr(buff,0x20),*timer;
  if (!begin || (uptr)getptr(buff,0x28)!=(uptr)begin+sizeof(void *)) return 0;
  timer=getptr(begin,0);
  return timer && getptr(timer,0)==time_vtable;
}
int qualifies(void *buff, void *actor) {
  if (!buff || !actor || !main_template(get32(buff,0x160),get32(buff,0x50))) return 0;
  if (*((u8 *)buff+0x86) || *((u8 *)buff+0x138)) return 0;
  return own_game(actor) && self_source(actor,get64(buff,0x130),*((u8 *)buff+0x138)) && single_timer(buff);
}
float held_delta(void *buff, void *actor, float delta) {
  return delta>0.0f && qualifies(buff,actor) ? 0.0f : delta;
}
void update_main(void *buff, void *actor, float delta) {
  ((void (*)(void *,void *,float))getptr(original_slot,0))(buff,actor,held_delta(buff,actor,delta));
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
  void *game,*first,*value_begin;u32 tick,i;
  union {float f;u32 u;} stamp;
  u64 (*original)(void *,void *,void *)=(u64 (*)(void *,void *,void *))getptr(restore_slot,0);
  if (!buff || !snapshot || !actor || !main_template(get32(snapshot,0x4e),get32(buff,0x50)) ||
      !self_source(actor,get64(snapshot,0x38),*((u8 *)snapshot+0x4d)) ||
      !single_timer(buff) || !(game=own_game(actor))) return original(buff,snapshot,actor);
  first=getptr(snapshot,0x18);
  if (!first || (uptr)getptr(snapshot,0x20)!=(uptr)first+28 || get32(first,0)!=1)
    return original(buff,snapshot,actor);
  value_begin=getptr(first,4);
  if (!value_begin || (uptr)getptr(first,12)!=(uptr)value_begin+12)
    return original(buff,snapshot,actor);
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
