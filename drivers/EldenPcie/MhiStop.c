/* SPDX-License-Identifier: GPL-2.0-only */
#include "MhiStop.h"
static int fail(EldenMhiStop *s,int rc){s->error=rc;return rc;}
static int live(const EldenMhiStopIo *io){
    int rc=io->admit(io->context);if(rc)return rc;uint32_t id=0;
    rc=elden_pcie_cfg_read(io->config,0,4,&id,true);return rc?rc:id==0x110e17cb?0:-19;
}
static int sample(EldenMhiStop *s,const EldenMhiStopIo *io){
    int rc=live(io);if(rc)return rc;
    rc=io->read(io->context,0x38,&s->control);if(rc)return rc;
    rc=io->read(io->context,0x48,&s->status);if(rc)return rc;
    return s->control==UINT32_MAX||s->status==UINT32_MAX?-19:0;
}
static int reset_state(const EldenMhiStop *s){
    unsigned state=(s->status>>8)&255;
    return !(s->control&2)&&!(s->status&4)&&(state==0||(state==1&&(s->status&1)));
}
int elden_mhi_stop(EldenMhiStop *s,const EldenMhiStopIo *io,uint64_t deadline){
    if(!s||!io||!io->config||!io->admit||!io->read||!io->write||!io->now_us||!io->delay_us)return -22;
    if(s->attempted)return s->error?s->error:s->phase==6?0:-16;
    s->attempted=1;s->phase=1;
    uint64_t begin=io->now_us(io->context);if(begin>=deadline)return fail(s,-110);
    int rc=live(io);if(rc)return fail(s,rc);
    rc=elden_pcie_cfg_read(io->config,4,2,&s->command,true);if(rc)return fail(s,rc);
    if((s->command&3)!=2)return fail(s,-71);
    if(!io->config->master_attempted){
        if(s->command&4)return fail(s,-16);
        s->master_off=s->transactions_idle=1;s->phase=6;return 0;
    }
    s->phase=2;if((rc=sample(s,io)))return fail(s,rc);
    if(!reset_state(s)){
        s->phase=3;
        if(!(s->control&2)){
            if(io->now_us(io->context)>=deadline)return fail(s,-110);
            s->reset_requested=1;
            if((rc=io->write(io->context,0x38,s->control|2)))return fail(s,rc);
        }
        for(unsigned i=0;;i++){
            if((rc=sample(s,io)))return fail(s,rc);
            if(reset_state(s))break;
            uint64_t now=io->now_us(io->context);
            if(now<begin||now>=deadline||now-begin>=2000000||i>=2000)return fail(s,-110);
            io->delay_us(io->context,1000);
        }
    }
    s->reset_observed=1;s->phase=4;
    if((rc=elden_pcie_cfg_master(io->config,false)))return fail(s,rc);
    s->phase=5;
    for(unsigned i=0;;i++){
        if((rc=live(io)))return fail(s,rc);
        if((rc=elden_pcie_cfg_read(io->config,4,2,&s->command,true)))return fail(s,rc);
        if((rc=elden_pcie_cfg_read(io->config,(int)0x8000000a,2,&s->device_status,true)))return fail(s,rc);
        if(s->command&4)return fail(s,-71);
        if(!(s->device_status&32))break;
        uint64_t now=io->now_us(io->context);
        if(now<begin||now>=deadline||i>=1000)return fail(s,-110);
        io->delay_us(io->context,1000);
    }
    if(io->now_us(io->context)>=deadline)return fail(s,-110);
    s->master_off=s->transactions_idle=1;s->phase=6;return 0;
}
