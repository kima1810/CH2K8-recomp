// Synthetic dispatch tests: compiled only here; remote operator runs explicitly.
// No game, native menu, textures, DLL loader, files, or user saves.
#include "../port/src/mod_framework.h"
#include <stdexcept>
using namespace ch2k8::mods;
static void check(bool value){if(!value)throw std::runtime_error("Presentation SDK contract failed");}
struct State{bool invalid=false;unsigned observations=0;};
static ChmodStatus CHMOD_CALL choose(void* user,ChmodCall* call){
 auto& s=*static_cast<State*>(user);
 const auto* a=static_cast<const ChmodButtonStyleArgs*>(call->arguments);
 auto* r=static_cast<ChmodButtonStyleResult*>(call->result);
 r->style=s.invalid?9:(a->current_style ^ (a->action==CHMOD_BUTTON_STYLE_TOGGLE));
 return CHMOD_OK;
}
static ChmodStatus CHMOD_CALL observe(void* user,ChmodCall*){++static_cast<State*>(user)->observations;return CHMOD_OK;}
int main(){
 auto& f=Framework::instance();State state;
 const auto* host=f.create_module("synthetic.presentation",{"hook.presentation.button_style"});
 check(host!=nullptr);
 check(f.initialize(host,[&]{
  ChmodRegistration token;
  ChmodRegistrationSpec s{sizeof(s),5,1,CHMOD_BEFORE,CHMOD_TRANSFORM,0,choose,&state};
  check(host->register_hook(host->session,&s,&token)==CHMOD_E_PHASE); // args immutable
  s.phase=CHMOD_AFTER;s.mode=CHMOD_REPLACEMENT;
  check(host->register_hook(host->session,&s,&token)!=CHMOD_OK);
  s.mode=CHMOD_OBSERVE;s.callback=observe;
  check(host->register_hook(host->session,&s,&token)==CHMOD_OK);
  s.mode=CHMOD_TRANSFORM;s.callback=choose;
  check(host->register_hook(host->session,&s,&token)==CHMOD_OK);return CHMOD_OK;
 })==CHMOD_OK);
 f.publish();
 auto dispatch=[&](uint32_t action,uint32_t prior){
  ChmodButtonStyleArgs args{action,prior};ChmodButtonStyleResult result{};unsigned original=0;
  auto d=typed_call(5,args,result,[&]{++original;result.style=0;},[&]{return args.action==action && args.current_style==prior && result.style<=1;});
  f.dispatch(d);check(original==1);return result.style;
 };
 check(dispatch(0,0)==0);check(dispatch(1,0)==1);check(dispatch(0,1)==1);check(dispatch(1,1)==0);
 state.invalid=true;check(dispatch(1,0)==0); // invalid result disables transformer
 state.invalid=false;check(dispatch(1,0)==0); // original fallback remains Xbox
 check(state.observations==6);
 f.stop();check(dispatch(1,1)==0);check(state.observations==6);
}
