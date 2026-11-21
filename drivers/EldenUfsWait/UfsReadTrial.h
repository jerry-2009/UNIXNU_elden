// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>

// This exact loop is used by the kernel adapter and the host fault tests.
// Modes alter waiting only: both retain IRQ delivery, DMA and completion proof.
// Firmware/cache state is not reset. Timings are warm pre-publication QD1 reads.
template<class IO>
bool eldenRunUfsReadTrial(IO &io, uint64_t totalBlocks) {
    if(totalBlocks<32||totalBlocks>0x100000000ULL||!io.ready())return false;
    const uint64_t deadline=io.now()+10000000000ULL; // <=10s per window
    bool good=true;
    unsigned sequence=0;
    for(unsigned warm=0;warm<2&&good;++warm) {
        const unsigned sites=warm?16:1;
        for(unsigned site=0;site<sites&&good;++site) {
            const uint64_t index=((uint64_t(site)*(totalBlocks-32))/15)&~31ULL;
            for(unsigned size=0;size<2&&good;++size) {
                const unsigned blocks=size?32:1;
                for(unsigned order=0;order<2&&good;++order) {
                    const unsigned mode=(site+order)&1; // alternate pair order
                    if(!io.ready()||io.now()>=deadline){good=false;break;}
                    io.polling(mode==0);
                    io.before();
                    const uint64_t started=io.now();
                    int result=io.read(index,blocks);
                    const uint64_t finished=io.now();
                    io.after();
                    io.polling(false);
                    if(result||finished<started||finished>deadline||!io.ready()) {good=false;break;}
                    for(unsigned block=0;block<blocks;++block) {
                        if(!io.verify(index+block,block)){good=false;break;}
                    }
                    if(!good)break;
                    // Verify and logging are outside the timed transport+copy.
                    if(warm)io.record(sequence++,mode,index,blocks,finished-started);
                }
            }
        }
    }
    io.polling(false);
    io.finish(good,sequence);
    return good;
}
