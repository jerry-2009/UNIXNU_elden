// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <cassert>
#include <cstdio>
#include <set>
#include <tuple>
#include "UfsReadTrial.h"
struct IO {
    uint64_t time=100,limit=1600;
    unsigned reads=0,verifies=0,records=0,ends=0,beforeCount=0,afterCount=0;
    unsigned failRead=0,failVerify=0,stopAt=0,slowAt=0,backAt=0;
    bool poll=false,reported=false;
    std::set<std::tuple<unsigned,uint64_t,unsigned>> seen;
    bool ready(){return !stopAt||reads<stopAt;}
    uint64_t now(){return time;}
    void polling(bool p){poll=p;}
    void before(){beforeCount++;}void after(){afterCount++;}
    int read(uint64_t index,unsigned blocks){
        assert(blocks==1||blocks==32);assert(index<=limit-blocks&&!(index&31));reads++;
        time+=slowAt==reads?11000000000ULL:100000;
        if(backAt==reads)time-=200000;
        return failRead==reads?1:0;
    }
    bool verify(uint64_t index,unsigned block){assert(index<limit&&block<32&&!poll);verifies++;return failVerify!=verifies;}
    void record(unsigned seq,unsigned mode,uint64_t index,unsigned blocks,uint64_t ns){
        assert(seq==records++&&mode<=1&&ns==100000&&!poll);
        assert(seen.insert({mode,index,blocks}).second);
    }
    void finish(bool good,unsigned n){assert(n==records&&!poll);reported=good;ends++;}
};
int main(){unsigned cases=0;IO ok;assert(eldenRunUfsReadTrial(ok,ok.limit));
    assert(ok.reads==68&&ok.records==64&&ok.verifies==1122&&ok.reported&&ok.ends==1);cases++;
    for(unsigned read=1;read<=68;read++)for(unsigned kind=0;kind<4;kind++){
        IO io;if(kind==0)io.failRead=read;if(kind==1)io.stopAt=read;if(kind==2)io.slowAt=read;if(kind==3)io.backAt=read;
        assert(!eldenRunUfsReadTrial(io,io.limit)&&!io.reported&&!io.poll&&io.reads==read&&io.ends==1);cases++;
    }
    for(unsigned at:{1u,33u,1122u}){IO io;io.failVerify=at;assert(!eldenRunUfsReadTrial(io,io.limit)&&!io.poll&&io.verifies==at&&!io.reported);cases++;}
    for(uint64_t size:{0ULL,31ULL,0x100000001ULL}){IO io;assert(!eldenRunUfsReadTrial(io,size)&&!io.reads&&!io.poll);cases++;}
    printf("PASS %u actual read-trial loop cases\n",cases);
}
