#pragma once
#include "abi.h"
#include <string_view>
namespace chmod {
inline const ChmodButtonStyleArgs* button_style_args(const ChmodCall* c){return c && c->hook==CHMOD_HOOK_BUTTON_STYLE && c->arguments_size==sizeof(ChmodButtonStyleArgs)?static_cast<const ChmodButtonStyleArgs*>(c->arguments):nullptr;}
inline ChmodButtonStyleResult* button_style_result(ChmodCall* c){return c && c->hook==CHMOD_HOOK_BUTTON_STYLE && c->result_size==sizeof(ChmodButtonStyleResult)?static_cast<ChmodButtonStyleResult*>(c->result):nullptr;}
class Host {
 const ChmodHostV2* api_{};
public:
 explicit Host(const ChmodHostV2* api):api_(api){}
 ChmodStatus hook(uint32_t index,ChmodHookInfo& out)const{out.size=sizeof(out);return api_->discover(api_->session,index,&out);}
 bool supports(const char* capability)const{return api_->has_capability(api_->session,capability)==CHMOD_OK;}
 ChmodStatus log(std::string_view message,uint32_t level=1)const{return api_->log(api_->session,level,message.data(),uint32_t(message.size()));}
 ChmodStatus add(uint32_t hook,uint32_t phase,uint32_t mode,ChmodCallback fn,void* user,ChmodRegistration& out,int order=0)const{
  const ChmodRegistrationSpec s{sizeof(s),hook,1,phase,mode,order,fn,user};return api_->register_hook(api_->session,&s,&out);
 }
 ChmodStatus remove(ChmodRegistration token)const{return api_->unregister_hook(api_->session,token);}
 ChmodStatus original(const ChmodCall& call)const{return api_->invoke_original(api_->session,call.invocation);}
 ChmodStatus weight(ChmodPlayer player,uint32_t& out)const{return api_->read_player_weight(api_->session,player,&out);}
 ChmodStatus pending_weight(ChmodPlayer player,uint32_t pounds)const{return api_->set_pending_weight(api_->session,player,pounds);}
};
/* Cast helpers check hook, stage-independent payload size, and never expose PPC. */
inline ChmodWeightReadArgs* weight_read(ChmodCall* c){return c && c->hook==CHMOD_HOOK_WEIGHT_READ && c->arguments_size==sizeof(ChmodWeightReadArgs)?static_cast<ChmodWeightReadArgs*>(c->arguments):nullptr;}
inline ChmodWeightWriteArgs* weight_write(ChmodCall* c){return c && c->hook==CHMOD_HOOK_WEIGHT_WRITE && c->arguments_size==sizeof(ChmodWeightWriteArgs)?static_cast<ChmodWeightWriteArgs*>(c->arguments):nullptr;}
inline ChmodWeightReadResult* weight_result(ChmodCall* c){return c && c->hook==CHMOD_HOOK_WEIGHT_READ && c->result_size==sizeof(ChmodWeightReadResult)?static_cast<ChmodWeightReadResult*>(c->result):nullptr;}
}
