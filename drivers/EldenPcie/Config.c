/* SPDX-License-Identifier: GPL-2.0-only */
#include "Config.h"
static int fail(EldenPcieConfigAccess *c,int rc){if(rc&&!c->error)c->error=rc;return rc;}
static int admit(EldenPcieConfigAccess *c,bool cleanup){
    if(!c||!c->io.admit||!c->io.read32||!c->io.write32||!c->io.master_ready)return -22;
    if(!cleanup&&c->error)return c->error;
    return c->io.admit(c->io.context,cleanup);
}
static int read_word(EldenPcieConfigAccess *c,uint32_t off,uint32_t *v,bool cleanup){
    int rc=admit(c,cleanup);if(rc)return rc;
    c->reads++;rc=c->io.read32(c->io.context,off,v);return rc?fail(c,rc):0;
}
static int write_word(EldenPcieConfigAccess *c,uint32_t off,uint32_t v,bool cleanup){
    int rc=admit(c,cleanup);if(rc)return rc;
    c->writes++;rc=c->io.write32(c->io.context,off,v);return rc?fail(c,rc):0;
}
static int address(EldenPcieConfigAccess *c,int input,int size,uint32_t *out){
    if(!c||!c->ready||(size!=1&&size!=2&&size!=4))return -22;
    uint32_t off=(uint32_t)input;
    if(off&0x80000000u){
        off&=0x7fffffffu;if(off>=0x3c)return -22;off+=c->pcie_cap;
    }
    if(off>4096u-(unsigned)size||(off&((unsigned)size-1)))return -22;
    *out=off;return 0;
}
int elden_pcie_cfg_open(EldenPcieConfigAccess *c,uint64_t sink){
    if(!c||!sink||sink>UINT32_MAX||(sink&4095))return -22;
    if(c->attempted)return -16;c->attempted=true;c->sink=sink;
    int rc=admit(c,false);if(rc)return fail(c,rc);
    uint32_t v=0;if((rc=read_word(c,0,&v,false)))return rc;
    if(v!=0x110e17cb)return fail(c,-19);
    if((rc=read_word(c,4,&v,false)))return rc;
    if((v&7)!=2)return fail(c,-16);c->command=v&0xffff;
    if((rc=read_word(c,0x34,&v,false)))return rc;
    uint32_t cap=v&255;uint64_t seen=0;
    for(unsigned i=0;cap;i++){
        if(i>=48||cap<0x40||cap>0xfc||(cap&3))return fail(c,-71);
        uint64_t bit=1ull<<(cap/4-16);if(seen&bit)return fail(c,-71);seen|=bit;
        if((rc=read_word(c,cap,&v,false)))return rc;
        if((v&255)==0x10){if(c->pcie_cap||cap>0xc4)return fail(c,-71);c->pcie_cap=cap;}
        if((v&255)==5){
            if(c->msi_cap||((v>>17)&7)>5||(v&(1u<<16)))return fail(c,-71);
            unsigned last=(v&(1u<<23))?12:8;if(v&(1u<<24))last+=4;
            if(cap+last>0xfc)return fail(c,-71);c->msi_cap=cap;c->msi_header=v;
        }
        cap=(v>>8)&255;
    }
    if(!c->pcie_cap||!c->msi_cap)return fail(c,-19);
    uint32_t msi_bytes=(c->msi_header&(1u<<23))?16:12;if(c->msi_header&(1u<<24))msi_bytes+=4;
    if(c->msi_cap<c->pcie_cap+20&&c->pcie_cap<c->msi_cap+msi_bytes)return fail(c,-71);
    if((rc=read_word(c,c->pcie_cap+16,&v,false)))return rc;
    if(v==UINT32_MAX)return fail(c,-19);
    c->initial_link_control=v&0xffff;c->link_control_saved=true;
    c->ready=true;return 0;
}
int elden_pcie_cfg_read(EldenPcieConfigAccess *c,int input,int size,uint32_t *value,bool cleanup){
    if(!value)return -22;uint32_t off=0;int rc=address(c,input,size,&off);if(rc)return rc;
    uint32_t word=0;rc=read_word(c,off&~3u,&word,cleanup);if(rc)return rc;
    unsigned shift=(off&3)*8;*value=size==4?word:(word>>shift)&(size==2?0xffffu:0xffu);return 0;
}
int elden_pcie_cfg_write(EldenPcieConfigAccess *c,int input,int size,uint32_t value,bool cleanup){
    uint32_t off=0;int rc=address(c,input,size,&off);if(rc)return rc;
    uint32_t word_off=off&~3u;
    if((size==1&&value>255)||(size==2&&value>65535))return -22;
    uint32_t old=0;if((rc=read_word(c,word_off,&old,cleanup)))return rc;
    unsigned shift=(off&3)*8;uint32_t mask=size==4?~0u:(size==2?0xffffu:0xffu)<<shift;
    uint32_t next=(old&~mask)|((value<<shift)&mask),verify_mask=mask;
    bool msi_control=word_off==c->msi_cap;
    bool aspm_restore=cleanup&&word_off==c->pcie_cap+16;
    if(cleanup&&!msi_control&&!aspm_restore)return -1;
    if(aspm_restore&&(!c->link_control_saved||size!=2||off!=word_off||
       ((next^old)&0xfffcu)||(next&3u)!=(c->initial_link_control&3u)))return -1;
    if(msi_control){
        /* Only Enable/MME are writable. Keep the actual capability/next/MMC/
         * width/PVM fields, and never allow a cleanup call to enable MSI. */
        if((next^old)&~0x00710000u)return -1;
        if((next&~0x00710000u)!=(c->msi_header&~0x00710000u))return fail(c,-71);
        if(cleanup&&(next&(1u<<16)))return -1;
        if(((next>>20)&7)>((old>>17)&7))return -22;
    }else if(word_off==c->msi_cap+4){if(next!=(uint32_t)c->sink)return -1;}
    else if((c->msi_header&(1u<<23))&&word_off==c->msi_cap+8){if(next)return -1;}
    else if(word_off==c->msi_cap+((c->msi_header&(1u<<23))?12u:8u)){
        if(size!=2||(off&3)||(next&0xffff)>31)return -1;
    }else if((c->msi_header&(1u<<24))&&word_off==c->msi_cap+((c->msi_header&(1u<<23))?16u:12u)){
        if(size!=4)return -1; /* all 32 vectors belong to the same endpoint */
    }else if(word_off==c->pcie_cap+8||word_off==c->pcie_cap+16){
        if(size!=2||off!=word_off)return -1;
        /* Device/Link Status occupy the high half and include W1C bits.
         * Writing a read-modify-write copy of them would acknowledge events. */
        next&=0xffff;verify_mask=0xffff;
    }else return -1;
    if((rc=write_word(c,word_off,next,cleanup)))return rc;
    uint32_t actual=0;if((rc=read_word(c,word_off,&actual,cleanup)))return rc;
    if((actual&verify_mask)!=(next&verify_mask))return fail(c,-71);
    return 0;
}
int elden_pcie_cfg_master(EldenPcieConfigAccess *c,bool enable){
    if(!c||!c->ready)return -22;
    int rc=admit(c,!enable);if(rc)return rc;
    if(enable&&(rc=c->io.master_ready(c->io.context)))return rc;
    uint32_t id=0,old=0;if((rc=read_word(c,0,&id,!enable)))return rc;
    if(id!=0x110e17cb)return fail(c,-19);
    if((rc=read_word(c,4,&old,!enable)))return rc;
    if((old&3)!=2)return fail(c,-71);
    if(enable)c->master_attempted=true;c->master_known=false;
    uint32_t command=(old&0xffff)&~4u;if(enable)command|=4;
    if((rc=write_word(c,4,command,!enable)))return rc;
    uint32_t actual=0;if((rc=read_word(c,4,&actual,!enable)))return rc;
    if((actual&0xffff)!=command)return fail(c,-71);
    c->command=command;c->master_known=true;return 0;
}
