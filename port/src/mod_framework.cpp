#include "mod_framework.h"
#include <algorithm>
#include <atomic>
#include <cfenv>
#include <condition_variable>
#include <cstring>
#include <mutex>
#include <set>
#include <unordered_map>
#ifdef _WIN32
#include <immintrin.h>
#endif
namespace ch2k8::mods {
namespace {
thread_local uint64_t initializing=0;
struct Frame { Dispatch* dispatch; Frame* parent; uint64_t invocation=0,owner=0; uint32_t phase=0,mode=0; bool called=false;std::vector<std::byte> original_result; };
thread_local Frame* current=nullptr;
std::string hook_cap(uint32_t hook){
 const std::string name=Framework::inventory().at(hook-1).name;
 return (name.starts_with("runtime.")?"lifecycle.":"hook.")+name;
}
struct FpGuard {
 std::fenv_t env{}; bool valid=std::fegetenv(&env)==0;
#ifdef _WIN32
 unsigned mxcsr=_mm_getcsr();
#endif
 ~FpGuard(){if(valid)std::fesetenv(&env);
#ifdef _WIN32
 _mm_setcsr(mxcsr);
#endif
 }
};
void copy_to(std::span<std::byte> target,const std::vector<std::byte>& source){if(!source.empty())std::memcpy(target.data(),source.data(),source.size());}
}
struct Framework::Module {std::string id;std::set<std::string> caps,replacements;ChmodHostV2 host;size_t order;};
struct Registration {ChmodRegistration id;uint64_t owner;size_t module_order;ChmodRegistrationSpec spec;std::atomic<bool> active{true};};
struct Framework::State {
 std::mutex mutex,gate;std::condition_variable drained;bool accepting=false;std::atomic<bool> stopped{false};size_t inflight=0;
 std::atomic<bool> published{false};std::atomic<uint64_t> serial{1};
 std::vector<std::shared_ptr<Module>> modules;std::vector<std::shared_ptr<Registration>> registrations;Logger logger;
 std::shared_ptr<Module> module(uint64_t session){for(auto& m:modules)if(m->host.session==session)return m;return {};}
};
Framework::Framework():state_(std::make_unique<State>()){}
Framework& Framework::instance(){static Framework f;return f;}
const std::vector<ChmodHookInfo>& Framework::inventory(){
 static const std::vector<ChmodHookInfo> v={
#include "mod_hook_inventory.inc"
 };
 return v;
}
std::vector<std::string> Framework::capabilities(){
 std::vector<std::string> out={"data.player.weight.read","data.player.weight.pending_write"};
 for(const auto& h:inventory())out.push_back(hook_cap(h.id));return out;
}
void Framework::logger(Logger l){state_->logger=std::move(l);}
const ChmodHostV2* Framework::create_module(std::string id,std::vector<std::string> caps,std::vector<std::string> replacements){
 std::lock_guard lock(state_->mutex);if(state_->published || state_->stopped || state_->modules.size()>=64)return nullptr;
 auto m=std::make_shared<Module>();m->id=std::move(id);m->caps.insert(caps.begin(),caps.end());m->order=state_->modules.size();
 m->replacements.insert(replacements.begin(),replacements.end());
 m->host={sizeof(ChmodHostV2),2,state_->serial++,discover,capability,add,remove,original,read_weight,set_weight,log};
 state_->modules.push_back(m);return &m->host;
}
ChmodStatus Framework::initialize(const ChmodHostV2* host,const std::function<ChmodStatus()>& fn){
 if(!host || initializing || current)return CHMOD_E_LIFETIME;
 initializing=host->session;ChmodStatus status=CHMOD_E_CALLBACK;
 try{FpGuard fp;if(fp.valid)status=fn();}catch(...){status=CHMOD_E_CALLBACK;}
 initializing=0;if(status!=CHMOD_OK)discard(host->session);return status;
}
void Framework::discard(uint64_t owner){std::lock_guard lock(state_->mutex);for(auto& r:state_->registrations)if(r->owner==owner)r->active=false;}
ChmodStatus Framework::discover(uint64_t session,uint32_t index,ChmodHookInfo* out){
 auto& s=*instance().state_;std::lock_guard lock(s.mutex);
 if(!s.module(session))return CHMOD_E_LIFETIME;
 if(!out || out->size!=sizeof(*out))return CHMOD_E_ARGUMENT;
 if(index>=inventory().size())return CHMOD_E_RANGE;*out=inventory()[index];return CHMOD_OK;
}
ChmodStatus Framework::capability(uint64_t session,const char* name){
 if(!name)return CHMOD_E_ARGUMENT;auto& s=*instance().state_;std::lock_guard lock(s.mutex);auto m=s.module(session);
 if(!m)return CHMOD_E_LIFETIME;
 // Negotiation is the intersection of runtime support and package declarations.
 const auto all=capabilities();const std::set<std::string> supported(all.begin(),all.end());
 return supported.contains(name) && m->caps.contains(name)?CHMOD_OK:CHMOD_E_CAPABILITY;
}
ChmodStatus Framework::add(uint64_t owner,const ChmodRegistrationSpec* spec,ChmodRegistration* out){
 if(!spec || !out || spec->size!=sizeof(*spec) || !spec->callback)return CHMOD_E_ARGUMENT;
 auto& s=*instance().state_;std::lock_guard lock(s.mutex);auto m=s.module(owner);
 if(!m || initializing!=owner || s.published || s.stopped)return CHMOD_E_LIFETIME;
 if(spec->hook<1 || spec->hook>inventory().size() || spec->hook_version!=1)return CHMOD_E_VERSION;
 if(!m->caps.contains(hook_cap(spec->hook)))return CHMOD_E_CAPABILITY;
 if(spec->mode==CHMOD_REPLACEMENT && !m->replacements.contains(inventory()[spec->hook-1].name))return CHMOD_E_CAPABILITY;
 if(spec->order<-10000 || spec->order>10000 || s.registrations.size()>=1024)return CHMOD_E_LIMIT;
 auto ops=inventory()[spec->hook-1].operations;
 if(spec->phase<1 || spec->phase>3 || !(ops&(1u<<(spec->phase-1))) || spec->mode>2)return CHMOD_E_PHASE;
 if((spec->phase==CHMOD_REPLACE)!=(spec->mode==CHMOD_REPLACEMENT))return CHMOD_E_PHASE;
 if(spec->mode==CHMOD_TRANSFORM && !((spec->phase==CHMOD_BEFORE && (ops&CHMOD_OP_ARGUMENTS)) || (spec->phase==CHMOD_AFTER && (ops&CHMOD_OP_RESULT))))return CHMOD_E_PHASE;
 if(spec->mode==CHMOD_REPLACEMENT)for(auto& r:s.registrations)if(r->active && r->spec.hook==spec->hook && r->spec.mode==CHMOD_REPLACEMENT)return CHMOD_E_CONFLICT;
 auto r=std::make_shared<Registration>();r->id=s.serial++;r->owner=owner;r->module_order=m->order;r->spec=*spec;s.registrations.push_back(r);*out=r->id;return CHMOD_OK;
}
ChmodStatus Framework::remove(uint64_t owner,ChmodRegistration id){
 auto& s=*instance().state_;std::lock_guard lock(s.mutex);
 if(initializing!=owner && (!current || current->owner!=owner))return CHMOD_E_LIFETIME;
 for(auto& r:s.registrations)if(r->id==id && r->owner==owner){r->active=false;return CHMOD_OK;}return CHMOD_E_ARGUMENT;
}
ChmodStatus Framework::original(uint64_t owner,uint64_t invocation){
 auto* f=current;if(!f || f->owner!=owner || f->invocation!=invocation)return CHMOD_E_LIFETIME;
 if(f->phase!=CHMOD_REPLACE || f->mode!=CHMOD_REPLACEMENT || !f->dispatch->original)return CHMOD_E_PHASE;
 if(!f->dispatch->validate())return CHMOD_E_RANGE;
 if(!f->called){f->dispatch->original();f->called=true;f->original_result.assign(f->dispatch->result.begin(),f->dispatch->result.end());}
 else copy_to(f->dispatch->result,f->original_result);
 return CHMOD_OK;
}
ChmodStatus Framework::read_weight(uint64_t owner,ChmodPlayer player,uint32_t* out){
 auto* f=current;if(!out)return CHMOD_E_ARGUMENT;
 if(!f || f->owner!=owner || !player || player!=f->dispatch->player)return CHMOD_E_LIFETIME;
 if(capability(owner,"data.player.weight.read")!=CHMOD_OK)return CHMOD_E_CAPABILITY;
 if(!f->dispatch->read_weight)return CHMOD_E_CAPABILITY;
 *out=f->dispatch->read_weight();return CHMOD_OK;
}
ChmodStatus Framework::set_weight(uint64_t owner,ChmodPlayer player,uint32_t pounds){
 auto* f=current;if(!f || f->owner!=owner || !player || player!=f->dispatch->player)return CHMOD_E_LIFETIME;
 if(capability(owner,"data.player.weight.pending_write")!=CHMOD_OK)return CHMOD_E_CAPABILITY;
 if(f->dispatch->hook!=2 || (f->phase!=CHMOD_BEFORE && f->phase!=CHMOD_REPLACE) || f->mode==CHMOD_OBSERVE || f->called)return CHMOD_E_PHASE;
 if(pounds<100 || pounds>400)return CHMOD_E_RANGE;
 reinterpret_cast<ChmodWeightWriteArgs*>(f->dispatch->arguments.data())->pounds=pounds;return CHMOD_OK;
}
ChmodStatus Framework::log(uint64_t owner,uint32_t level,const char* message,uint32_t length){
 if(!message || length>4096 || level>3)return CHMOD_E_ARGUMENT;
 auto& s=*instance().state_;std::shared_ptr<Module> m;{std::lock_guard lock(s.mutex);m=s.module(owner);}
 if(!m)return CHMOD_E_LIFETIME;
 if(s.logger)s.logger(level,m->id+": "+std::string(message,length));return CHMOD_OK;
}
bool Framework::enabled()const{return state_->published.load(std::memory_order_acquire);}
ChmodPlayer Framework::next_player(){return state_->serial++;}
void Framework::publish(){
 {std::lock_guard lock(state_->gate);state_->accepting=true;state_->published=true;}
 Dispatch event{3,{},{},{},[]{return true;},{}};dispatch(event);
}
void Framework::stop(){
 bool was_published=false;
 {std::unique_lock lock(state_->gate);if(state_->stopped)return;state_->stopped=true;state_->accepting=false;was_published=state_->published.exchange(false);state_->drained.wait(lock,[&]{return state_->inflight==0;});}
 // Only shutdown thread can dispatch this terminal notification.
 if(was_published){Dispatch event{4,{},{},{},[]{return true;},{}};dispatch(event);}
 std::lock_guard lock(state_->mutex);for(auto& r:state_->registrations)r->active=false;
}
void Framework::dispatch(Dispatch& d){
 for(auto* p=current;p;p=p->parent)if(p->dispatch->hook==d.hook){if(d.original)d.original();return;}
 bool bypass=false;
 {std::lock_guard lock(state_->gate);bypass=!state_->accepting && d.hook!=4;if(!bypass)++state_->inflight;}
 if(bypass){if(d.original)d.original();return;}
 struct Flight{State& s;~Flight(){std::lock_guard lock(s.gate);if(--s.inflight==0)s.drained.notify_all();}}flight{*state_};
 std::vector<std::shared_ptr<Registration>> list;
 {std::lock_guard lock(state_->mutex);for(auto& r:state_->registrations)if(r->active && r->spec.hook==d.hook)list.push_back(r);}
 std::stable_sort(list.begin(),list.end(),[](const auto& a,const auto& b){if(a->module_order!=b->module_order)return a->module_order<b->module_order;if(a->spec.order!=b->spec.order)return a->spec.order<b->spec.order;return a->id<b->id;});
 Frame frame{&d,current};current=&frame;
 struct Scope{Frame* parent;~Scope(){current=parent;}}scope{frame.parent};
 auto invoke=[&](const std::shared_ptr<Registration>& r,uint32_t phase){
  if(!r->active || r->spec.phase!=phase)return false;
  std::vector<std::byte> args(d.arguments.begin(),d.arguments.end()),result(d.result.begin(),d.result.end());
  frame.owner=r->owner;frame.phase=phase;frame.mode=r->spec.mode;frame.invocation=state_->serial++;
  ChmodCall call{sizeof(ChmodCall),d.hook,phase,0,frame.invocation,d.arguments.data(),d.result.data(),uint32_t(d.arguments.size()),uint32_t(d.result.size())};
  ChmodStatus status=CHMOD_E_CALLBACK;try{FpGuard fp;if(fp.valid)status=r->spec.callback(r->spec.user,&call);}catch(...){status=CHMOD_E_CALLBACK;}
  bool valid=d.validate() && (phase!=CHMOD_REPLACE || !d.validate_result || d.validate_result());
  if(r->spec.mode==CHMOD_OBSERVE || status!=CHMOD_OK || !valid){
   copy_to(d.arguments,args);
   if(frame.called && phase==CHMOD_REPLACE)copy_to(d.result,frame.original_result);else copy_to(d.result,result);
  }
  if(status!=CHMOD_OK || !valid){r->active=false;if(state_->logger)state_->logger(3,"Disabled failed registration "+std::to_string(r->id));}
  frame.owner=0;frame.invocation=0;
  return status==CHMOD_OK && valid;
 };
 if(d.original){
  for(auto& r:list)invoke(r,CHMOD_BEFORE);
  auto replacement=std::find_if(list.begin(),list.end(),[](auto& r){return r->active && r->spec.phase==CHMOD_REPLACE;});
  bool replaced=replacement!=list.end() && invoke(*replacement,CHMOD_REPLACE);
  if(!replaced && !frame.called){d.original();frame.called=true;}
 }
 for(auto& r:list)invoke(r,CHMOD_AFTER);
}
}
