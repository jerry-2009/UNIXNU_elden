// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "BatchTrial.h"
#include <cassert>
#include <cstdio>
struct IO {
    unsigned issues=0,awaits=0,verifies=0,ends=0,active=0,peak=0,failAt=0,failKind=0,failed=0;
    unsigned depthValue=0,sizeValue=0,passValue=0,inGroup=0;uint64_t ticks=0,blocks[32]={};bool taken[32]={};
    bool ready(){return !failed;}
    bool depth(unsigned n){return n<=32;}
    uint64_t now(){return ticks;}
    void begin(unsigned d,unsigned n,unsigned p){assert(!active);depthValue=d;sizeValue=n;passValue=p;inGroup=0;}
    bool issue(unsigned i,uint64_t b,unsigned n){assert(i<depthValue&&!taken[i]&&n==sizeValue);issues++;if(failKind==1&&issues==failAt)return false;
        taken[i]=true;blocks[i]=b;active++;if(active>peak)peak=active;inGroup++;ticks+=100;return true;}
    bool await(unsigned i){assert(taken[i]&&inGroup==depthValue);awaits++;ticks+=100;if(failKind==2&&awaits==failAt)return false;return true;}
    bool verify(unsigned i,uint64_t b,unsigned n){assert(taken[i]&&blocks[i]==b&&n==sizeValue);verifies++;return !(failKind==3&&verifies==failAt);}
    void sample(uint64_t n){assert(n>0);}
    void cleanup(){for(unsigned i=0;i<32;i++)taken[i]=false;active=0;inGroup=0;}
    void fail(unsigned n){failed=n;}
    void end(){assert(!active);ends++;}
};
int main(){unsigned cases=0;IO io;assert(eldenRunBatchTrial(io,1483776)&&io.issues==768&&io.awaits==768&&io.verifies==768&&io.ends==24&&io.peak==32);cases++;
    for(unsigned kind=1;kind<=3;kind++)for(unsigned at=1;at<=768;at++){IO f;f.failKind=kind;f.failAt=at;assert(!eldenRunBatchTrial(f,1483776)&&f.failed&&!f.active);cases++;}
    printf("PASS %u batch sequencing/failure cases\n",cases);
}
