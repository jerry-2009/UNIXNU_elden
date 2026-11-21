/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* SM8750 GPIO16: exact TB322FC DTS pinctrl is GPIO, pull-up, 16mA.
 * Offsets/fields from pinned pinctrl-sm8750 + pinctrl-msm6f97250e.
 * Map ONLY GPIO16's page. Caller serializes all accesses with the WCN owner.
 * No PERST, wake, SW_CTRL, interrupt or other pin is changed here. */
typedef struct {
    void *context;
    int (*read)(void *,unsigned,uint32_t *);
    int (*write)(void *,unsigned,uint32_t);
    void (*delay_us)(void *,unsigned);
    bool initialized,held;
} EldenWlanGpio;

static inline int elden_wlan_gpio_set(EldenWlanGpio *g,bool high){
    if(!g||!g->read||!g->write||!g->delay_us)return -22;
    if(g->held)return -71;
    uint32_t ctl=0,io=0,irq=0;int rc=g->read(g->context,0,&ctl);
    if(!rc)rc=g->read(g->context,4,&io);
    if(!rc)rc=g->read(g->context,8,&irq);
    if(rc)return rc;
    /* Existing IRQ, non-GPIO mux or remote eGPIO ownership needs a separate
     * handoff. Never claim it by guessing. Input-high before first claim is an
     * unknown running boot consumer, even if its output latch differs. */
    if(ctl==UINT32_MAX||io==UINT32_MAX||irq==UINT32_MAX||(ctl&0x3cu)||
       (irq&1u)||((ctl&0x800u)&&!(ctl&0x1000u)))return -19;
    if(!g->initialized){
        if(high||(io&1u))return -19;
        /* Like msm_gpio_direction_output: low latch precedes output enable. */
        rc=g->write(g->context,4,io&~2u);
        if(!rc)rc=g->write(g->context,0,(ctl&~0x3ffu)|0x3c3u);
        if(!rc)rc=g->read(g->context,0,&ctl);
        if(!rc&&(ctl&0x3ffu)!=0x3c3u)rc=-71;
        if(rc){g->held=true;return rc;}
        g->initialized=true;
    }else if((ctl&0x3ffu)!=0x3c3u){g->held=true;return -71;}
    rc=g->write(g->context,4,high?io|2u:io&~2u);
    if(rc){g->held=true;return rc;}
    for(unsigned n=0;n<1000;n++){
        rc=g->read(g->context,4,&io);
        if(rc)break;
        if(io==UINT32_MAX){rc=-5;break;}
        if(((io&2u)!=0)!=high){rc=-71;break;}
        if(((io&1u)!=0)==high)return 0;
        g->delay_us(g->context,1);
    }
    g->held=true;return rc?rc:-110;
}
