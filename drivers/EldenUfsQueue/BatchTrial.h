// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
// Equal data/work at QD1/8/32. Timing covers issue/await only; verification and
// logs run outside that interval. Any failure retains uncertain DMA via cleanup.
template<class IO> bool eldenRunBatchTrial(IO &io,uint64_t totalBlocks){
    if(totalBlocks<32||totalBlocks>0x100000000ULL)return false;
    const unsigned depths[]={1,8,32},sizes[]={1,32};uint64_t limit=io.now()+30000000000ULL;
    for(unsigned size:sizes)for(unsigned pass=0;pass<4;pass++)for(unsigned depth:depths){
        if(!io.ready()||!io.depth(depth)){io.fail(1);return false;}
        io.begin(depth,size,pass);
        for(unsigned first=0;first<32;first+=depth){
            if(!io.ready()||io.now()>=limit){io.fail(2);io.cleanup();return false;}
            uint64_t started=io.now();
            for(unsigned i=0;i<depth;i++){
                uint64_t block=(uint64_t(pass*32+first+i)*(totalBlocks-32)/127)&~31ULL;
                if(!io.issue(i,block,size)){io.fail(3);io.cleanup();return false;}
            }
            for(unsigned i=0;i<depth;i++)if(!io.await(i)){io.fail(4);io.cleanup();return false;}
            uint64_t finished=io.now();
            if(finished<started||finished>limit){io.fail(5);io.cleanup();return false;}
            io.sample(finished-started);
            for(unsigned i=0;i<depth;i++){
                uint64_t block=(uint64_t(pass*32+first+i)*(totalBlocks-32)/127)&~31ULL;
                if(!io.verify(i,block,size)){io.fail(6);io.cleanup();return false;}
            }
            io.cleanup();
        }
        io.end();
    }
    return true;
}
