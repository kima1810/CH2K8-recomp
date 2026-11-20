// Synthetic framework contract tests. Compile permitted; DO NOT RUN automatically.
// No guest PPC, game process, DLL loading, user files, or real saves.
#include "../port/src/mod_framework.h"
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace ch2k8::mods;
void check(bool value){if(!value)throw std::runtime_error("framework contract failed");}
struct Fixture {
 const ChmodHostV2* host{};std::vector<int>* order{};int tag=0;bool fail=false;
 ChmodRegistration token{};ChmodPlayer stale=0;bool nested=false;
};
ChmodStatus CHMOD_CALL observe(void* user,ChmodCall* call){auto& f=*static_cast<Fixture*>(user);f.order->push_back(f.tag);return CHMOD_OK;}
ChmodStatus CHMOD_CALL transform(void* user,ChmodCall* call){auto& f=*static_cast<Fixture*>(user);f.order->push_back(f.tag);auto* r=static_cast<ChmodWeightReadResult*>(call->result);r->pounds+=f.tag;return f.fail?CHMOD_E_CALLBACK:CHMOD_OK;}
ChmodStatus CHMOD_CALL replace(void* user,ChmodCall* call){
 auto& f=*static_cast<Fixture*>(user);f.order->push_back(f.tag);
 if(f.fail)return CHMOD_E_CALLBACK;
 if(f.nested){
  ChmodWeightReadArgs args{Framework::instance().next_player()};ChmodWeightReadResult result{};int count=0;
  Dispatch nested{1,bytes(args),bytes(result),[&]{++count;result.pounds=123;},[]{return true;},{},args.player};
  Framework::instance().dispatch(nested);check(count==1 && result.pounds==123);
 }
 check(f.host->invoke_original(f.host->session,call->invocation)==CHMOD_OK);
 check(f.host->invoke_original(f.host->session,call->invocation)==CHMOD_OK);
 return CHMOD_OK;
}
ChmodStatus CHMOD_CALL write_args(void* user,ChmodCall* call){
 auto& f=*static_cast<Fixture*>(user);auto* a=static_cast<ChmodWeightWriteArgs*>(call->arguments);f.stale=a->player;
 check(f.host->set_pending_weight(f.host->session,a->player,210)==CHMOD_OK);
 uint32_t weight=0;check(f.host->read_player_weight(f.host->session,a->player,&weight)==CHMOD_OK && weight==200);
 return CHMOD_OK;
}
int main(){
 auto& core=Framework::instance();std::vector<int> order;
 auto caps=std::vector<std::string>{"hook.player.weight.read","hook.player.weight.write","data.player.weight.read","data.player.weight.pending_write","lifecycle.runtime.ready","lifecycle.runtime.stopping"};
 const auto* a=core.create_module("synthetic.a",caps,{"player.weight.read"});
 const auto* b=core.create_module("synthetic.b",caps,{"player.weight.read"});
 Fixture before{a,&order,1},replacement{a,&order,2},afterA{a,&order,3},afterB{b,&order,4},writer{a,&order},ready{a,&order,8},stopping{a,&order,9};
 auto add=[&](Fixture& f,uint32_t hook,uint32_t phase,uint32_t mode,ChmodCallback fn,int priority=0){ChmodRegistrationSpec s{sizeof(s),hook,1,phase,mode,priority,fn,&f};return f.host->register_hook(f.host->session,&s,&f.token);};
 check(core.initialize(a,[&]{
  check(add(before,1,CHMOD_BEFORE,CHMOD_OBSERVE,observe)==CHMOD_OK);
  check(add(replacement,1,CHMOD_REPLACE,CHMOD_REPLACEMENT,replace)==CHMOD_OK);
  check(add(afterA,1,CHMOD_AFTER,CHMOD_TRANSFORM,transform)==CHMOD_OK);
  check(add(writer,2,CHMOD_BEFORE,CHMOD_TRANSFORM,write_args)==CHMOD_OK);
  check(add(ready,3,CHMOD_AFTER,CHMOD_OBSERVE,observe)==CHMOD_OK);
  check(add(stopping,4,CHMOD_AFTER,CHMOD_OBSERVE,observe)==CHMOD_OK);
  return CHMOD_OK;
 })==CHMOD_OK);
 check(core.initialize(b,[&]{
  Fixture conflict{b,&order};check(add(conflict,1,CHMOD_REPLACE,CHMOD_REPLACEMENT,replace)==CHMOD_E_CONFLICT);
  Fixture invalid{b,&order};check(add(invalid,1,CHMOD_BEFORE,CHMOD_TRANSFORM,transform)==CHMOD_E_PHASE);
  check(add(afterB,1,CHMOD_AFTER,CHMOD_TRANSFORM,transform)==CHMOD_OK);return CHMOD_OK;
 })==CHMOD_OK);
 ChmodHookInfo info{sizeof(info)};check(a->discover(a->session,0,&info)==CHMOD_OK && info.id==1);
 check(a->has_capability(a->session,"simulation.unknown")==CHMOD_E_CAPABILITY);
 core.publish();check(order==std::vector<int>{8});order.clear();
 int originals=0;ChmodWeightReadArgs args{core.next_player()};ChmodWeightReadResult result{};
 Dispatch read{1,bytes(args),bytes(result),[&]{++originals;result.pounds=200;},[&]{return result.pounds<=400;},[]{return 200u;},args.player};
 core.dispatch(read);check(result.pounds==207 && originals==1 && order==std::vector<int>({1,2,3,4}));
 afterB.fail=true;order.clear();core.dispatch(read);check(result.pounds==203 && originals==2); // failed transform rolls back and disables itself
 afterB.fail=false;order.clear();core.dispatch(read);check(result.pounds==203 && order==std::vector<int>({1,2,3}));
 ChmodWeightWriteArgs wa{core.next_player(),200,0};uint32_t stored=200;
 Dispatch write{2,bytes(wa),{},[&]{stored=wa.pounds;},[&]{return wa.pounds>=100 && wa.pounds<=400;},[]{return 200u;},wa.player};
 core.dispatch(write);check(stored==210);
 uint32_t ignored=0;check(a->read_player_weight(a->session,writer.stale,&ignored)==CHMOD_E_LIFETIME);
 check(a->unregister_hook(a->session,before.token)==CHMOD_E_LIFETIME);
 check(core.initialize(a,[&]{check(a->unregister_hook(a->session,before.token)==CHMOD_OK);return CHMOD_OK;})==CHMOD_OK);
 order.clear();core.dispatch(read);check(order==std::vector<int>({2,3}));
 replacement.nested=true;order.clear();core.dispatch(read);check(order==std::vector<int>({2,3}));
 replacement.fail=true;order.clear();core.dispatch(read);check(result.pounds==203 && order==std::vector<int>({2,3}));
 order.clear();core.dispatch(read);check(result.pounds==203 && order==std::vector<int>({3}));
 core.stop();check(order.back()==9);const auto size=order.size();core.stop();check(order.size()==size);
 core.dispatch(read);check(order.size()==size && result.pounds==200);
 std::cout<<"synthetic framework contract cases passed\n";
}
