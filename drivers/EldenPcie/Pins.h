/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    void *context;
    int (*read)(void *,unsigned offset,uint32_t *);
    int (*write)(void *,unsigned offset,uint32_t);
    void (*delay_us)(void *,unsigned);
    bool initialized,held;
} EldenPciePins;
/* Window starts at GPIO102; GPIO103 is at +0x1000. Exact SM8750 default:
 * PERST GPIO/2mA/pulldown/output; CLKREQ function1/2mA/pullup/input. */
static inline int elden_pcie_pins_set(EldenPciePins *p,bool high){
    if(!p||!p->read||!p->write||!p->delay_us)return -22;
    if(p->held)return -71;
    if(high&&!p->initialized)return -11;
    uint32_t ctl[2]={0},irq[2]={0},io=0;int rc=0;
    for(unsigned i=0;i<2;i++){
        if((rc=p->read(p->context,i*0x1000,&ctl[i]))||(rc=p->read(p->context,i*0x1000+8,&irq[i])))return rc;
        if(ctl[i]==UINT32_MAX||irq[i]==UINT32_MAX||(irq[i]&1u)||((ctl[i]&0x800u)&&!(ctl[i]&0x1000u)))return -19;
        unsigned mux=(ctl[i]>>2)&15u;
        if((i==0&&mux)||(i==1&&mux>1))return -19;
    }
    if((rc=p->read(p->context,4,&io)))return rc;
    if(io==UINT32_MAX)return -5;
    if(!p->initialized){
        if((rc=p->write(p->context,4,io&~2u))||
           (rc=p->write(p->context,0,(ctl[0]&~0x3ffu)|0x201u))||
           (rc=p->write(p->context,0x1000,(ctl[1]&~0x3ffu)|7u))){p->held=true;return rc;}
        for(unsigned i=0;i<2;i++){
            rc=p->read(p->context,i*0x1000,&ctl[i]);
            if(rc||(ctl[i]&0x3ffu)!=(i?7u:0x201u)){p->held=true;return rc?rc:-71;}
        }
        p->initialized=true;
    }else if((ctl[0]&0x3ffu)!=0x201u||(ctl[1]&0x3ffu)!=7u){p->held=true;return -71;}
    rc=p->write(p->context,4,high?io|2u:io&~2u);
    if(rc){p->held=true;return rc;}
    for(unsigned n=0;n<1000;n++){
        rc=p->read(p->context,4,&io);if(rc)break;
        if(io==UINT32_MAX){rc=-5;break;}
        if(((io&2u)!=0)!=high){rc=-71;break;}
        if(((io&1u)!=0)==high)return 0;
        p->delay_us(p->context,1);
    }
    p->held=true;return rc?rc:-110;
}
