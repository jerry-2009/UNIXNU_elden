/* SPDX-License-Identifier: GPL-2.0-only */
#include "PlatformFence.h"
static int fail(EldenPlatformFence *s,int rc){s->error=rc;return rc;}
static int identify(EldenPlatformFence *s,const EldenPlatformFenceIo *io){
    int rc=io->admit(io->context);if(rc)return rc;
    rc=elden_pcie_cfg_read(io->config,0,4,&s->identity,true);
    return rc?rc:s->identity==0x110e17cb?0:-19;
}
int elden_pcie_platform_fence(EldenPlatformFence *s,const EldenPlatformFenceIo *io,uint64_t deadline){
    if(!s||!io||!io->config||!io->admit||!io->now_us||!io->delay_us)return -22;
    if(s->attempted)return s->error?s->error:s->phase==3?0:-16;
    s->attempted=1;s->phase=1;
    uint64_t begin=io->now_us(io->context);if(begin>=deadline)return fail(s,-110);
    int rc=identify(s,io);if(rc)return fail(s,rc);
    rc=elden_pcie_cfg_master(io->config,false);if(rc)return fail(s,rc);
    s->phase=2;
    for(unsigned i=0;;i++){
        if((rc=identify(s,io)))return fail(s,rc);
        if((rc=elden_pcie_cfg_read(io->config,4,2,&s->command,true)))return fail(s,rc);
        if((s->command&7)!=2)return fail(s,-71);
        s->master_off=1;
        if((rc=elden_pcie_cfg_read(io->config,(int)0x8000000a,2,&s->device_status,true)))return fail(s,rc);
        s->transactions_sampled=1;
        if(!(s->device_status&32)){s->transactions_idle=1;break;}
        uint64_t now=io->now_us(io->context);
        if(now<begin||now>=deadline||i>=1000)return fail(s,-110);
        io->delay_us(io->context,1000);
    }
    if(io->now_us(io->context)>=deadline)return fail(s,-110);
    s->phase=3;return 0;
}
