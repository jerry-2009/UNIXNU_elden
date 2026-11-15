// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "Ah8Control.h"
#include <cassert>
#include <cstdio>
#include <vector>
#include <utility>
struct IO {
    uint32_t reg[64]={};bool available=true,activeFlag=false,wakeGood=true;
    unsigned writes=0,wakes=0,dropWrite=0;std::vector<std::pair<unsigned,uint32_t>> log;
    IO(){reg[0]=0x00800000;reg[0xe4/4]=0x60000000;reg[0xc0/4]=300;reg[0x30/4]=0x10f;reg[0x60/4]=1;reg[0x24/4]=1;reg[0xfc/4]=0xa5000000;}
    bool idle(){return available;}
    uint32_t read(unsigned offset){assert(offset%4==0&&offset<256);return reg[offset/4];}
    void write(unsigned offset,uint32_t value){assert(offset==0xfc||offset==0x24||offset==0x18);writes++;log.push_back({offset,value});if(writes!=dropWrite)reg[offset/4]=value;}
    void active(bool on){activeFlag=on;}
    bool wake(){assert(!activeFlag&&!reg[0x18/4]&&reg[0x24/4]==1);wakes++;return wakeGood;}
};
int main(){unsigned cases=0;
    assert((EldenAh8Control::timer&1023)*10==5000&&((EldenAh8Control::timer>>10)&7)==1);
    {IO io;EldenAh8Control s;assert(s.start(io)==0&&s.phase==s.Enabled&&io.activeFlag&&io.reg[0x18/4]==0x5f4&&io.reg[0x24/4]==0x61);
     assert(io.log.size()==3&&io.log[0].first==0xfc&&io.log[1].first==0x24&&io.log[2].first==0x18);
     unsigned writes=io.writes;assert(s.start(io)==0&&io.writes==writes);assert(s.stop(io)==0&&s.phase==s.Restored&&!io.activeFlag&&io.wakes==1&&io.reg[0xfc/4]==0xa5000000);cases++;}
    for(unsigned field:{0u,0xe4u,0xc0u,0x30u,0x58u,0x78u,0x60u,0x20u,0x24u,0x18u}){
        IO io;EldenAh8Control s;io.reg[field/4]=(field==0x58||field==0x78||field==0x18)?1u:field==0x20?0x60u:0u;
        assert(s.start(io)<0&&!io.writes&&!io.activeFlag&&s.phase==s.Fresh);cases++;
    }
    {IO io;EldenAh8Control s;io.available=false;assert(s.start(io)==-1&&!io.writes);cases++;}
    for(unsigned offset:{0x58u,0x78u}){IO io;EldenAh8Control s;assert(s.start(io)==0);unsigned writes=io.writes;io.reg[offset/4]=1;assert(s.stop(io)==-1&&io.writes==writes&&io.activeFlag);cases++;}
    for(unsigned fail=1;fail<=3;fail++){
        IO io;EldenAh8Control s;io.dropWrite=fail;assert(s.start(io)<0&&s.phase==s.Held);
        io.dropWrite=0;assert(s.stop(io)==0&&s.phase==s.Restored&&!io.activeFlag&&io.reg[0xfc/4]==0xa5000000);cases++;
    }
    for(unsigned fail=1;fail<=3;fail++){
        IO io;EldenAh8Control s;assert(s.start(io)==0);io.dropWrite=io.writes+fail;
        assert(s.stop(io)<0&&s.phase==s.Held);if(fail<3)assert(!io.wakes);cases++;
    }
    {IO io;EldenAh8Control s;assert(s.start(io)==0);io.available=false;unsigned writes=io.writes;assert(s.stop(io)==-1&&io.writes==writes&&io.activeFlag);cases++;}
    {IO io;EldenAh8Control s;assert(s.start(io)==0);io.wakeGood=false;assert(s.stop(io)==-10&&s.phase==s.Held&&(io.reg[0xfc/4]&0x3c)==0x3c);cases++;}
    {IO io;EldenAh8Control s;assert(s.start(io)==0);io.reg[0x20/4]=0x20;assert(s.stop(io)==-10&&!io.wakes);cases++;}
    for(uint32_t mask=0;mask<64;mask++){
        IO io;EldenAh8Control s;io.reg[0xfc/4]=0xa5000000|mask;uint32_t before=io.reg[0xfc/4];
        assert(s.start(io)==0);io.reg[0xfc/4]^=0x40000000;assert(s.stop(io)==0);
        assert((io.reg[0xfc/4]&0x3c)==(before&0x3c)&&(io.reg[0xfc/4]&~0x3c)==((before^0x40000000)&~0x3c));cases++;
    }
    printf("PASS %u AH8 admission/write-order/failure/restore cases\n",cases);
}
