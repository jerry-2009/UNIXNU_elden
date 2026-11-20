/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#include <stdbool.h>
/* TB322FC/SM8750: pinctrl-sm8750, pinctrl-msm and the original stock GPIO
 * observation. GPIO18/19 func1, HOST_SOL202 output-low/4mA/pulldown. */
typedef struct {
    void *context;
    int (*read)(void *,unsigned,unsigned,uint32_t *);
    int (*write)(void *,unsigned,unsigned,uint32_t);
    bool attempted,ready,held;
    uint32_t before[3][3],after[3][3];
    unsigned writes;
} EldenWifiSideband;
static inline int elden_wifi_sideband_prepare(EldenWifiSideband *p)
{
    if(!p||!p->read||!p->write)return -22;
    if(p->attempted)return -16;
    p->attempted=true;
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++){
        int rc=p->read(p->context,i,j*4,&p->before[i][j]);if(rc)return rc;
    }
    for(unsigned i=0;i<3;i++){
        uint32_t ctl=p->before[i][0],io=p->before[i][1],irq=p->before[i][2];
        unsigned mux=(ctl>>2)&15;
        if(ctl==UINT32_MAX||io==UINT32_MAX||irq==UINT32_MAX||(irq&1)||
           ((ctl&0x800)&&!(ctl&0x1000))||(i<2?mux>1:(mux!=0)))return -19;
        /* These two signals belong to the target; do not drive them. */
        if(i<2&&(ctl&(1u<<9)))return -19;
    }
    for(unsigned i=0;i<3;i++){
        uint32_t wanted=i<2?(p->before[i][0]&~0x3cu)|4u:
            (p->before[i][0]&~0x3ffu)|0x241u;
        if(i==2){
            p->writes++;int rc=p->write(p->context,i,4,p->before[i][1]&~2u);
            if(rc){p->held=true;return rc;}
        }
        if(wanted!=p->before[i][0]){
            p->writes++;int rc=p->write(p->context,i,0,wanted);
            if(rc){p->held=true;return rc;}
        }
        for(unsigned j=0;j<3;j++){
            int rc=p->read(p->context,i,j*4,&p->after[i][j]);
            if(rc){p->held=p->writes!=0;return rc;}
        }
        if(p->after[i][0]!=wanted||p->after[i][2]!=p->before[i][2]||
           (i==2&&(p->after[i][1]&3u))){p->held=p->writes!=0;return -71;}
    }
    p->ready=true;return 0;
}
