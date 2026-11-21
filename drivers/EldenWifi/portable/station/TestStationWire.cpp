/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Check the actual derived wire against the loaded OEM's independent TLV
 * lengths/order and the vendor non-MLO contract. Register/MMIO not exercised.
 */
#include "../upstream/WifiAssoc.h"
#include <cassert>
#include <cstring>
using namespace pianowifi;
static WmiTlvRef next(const uint8_t *&p,uint32_t &left,uint32_t tag,uint32_t bytes){
    WmiTlvRef r;assert(wmiNext(p,left,r));assert(r.tag==tag&&r.length==bytes);return r;
}
static void zero(const uint8_t *p,unsigned bytes){for(unsigned i=0;i<bytes;i++)assert(!p[i]);}
int main(){
    unsigned cases=0;uint8_t bytes[768],own[6]={2,1,2,3,4,5};WmiWriter w;
    for(unsigned id=0;id<4;id++){
        VdevStart s;s.vdevId=id;s.freq=s.centerFreq=5180;s.txStreams=s.rxStreams=2;
        const auto n=assocBuildVdevStart(w,bytes,sizeof(bytes),s);
        assert(n==188);const uint8_t *p=bytes+4;uint32_t left=n-4;
        auto fixed=next(p,left,0x58,128);assert(wmiGet(fixed.value,0)==id);zero(fixed.value+112,16);
        next(p,left,0x50,24);next(p,left,18,0);
        auto mlo=next(p,left,18,12);assert(wmiGet(mlo.value,0)==0x03d60008);zero(mlo.value+4,8);
        next(p,left,18,0);assert(left==0);cases++;
        for(unsigned cap=0;cap<n;cap++){assert(!assocBuildVdevStart(w,bytes,cap,s));cases++;}
        const auto up=assocBuildVdevUp(w,bytes,sizeof(bytes),id,21,own);
        assert(up==44);p=bytes+4;left=up-4;fixed=next(p,left,0x5c,36);
        assert(wmiGet(fixed.value,0)==id&&wmiGet(fixed.value,1)==21);
        assert(!std::memcmp(fixed.value+8,own,6));zero(fixed.value+16,20);assert(!left);cases++;
        for(unsigned cap=0;cap<up;cap++){assert(!assocBuildVdevUp(w,bytes,cap,id,21,own));cases++;}
    }
    for(unsigned rate_count=1;rate_count<=16;rate_count++)for(unsigned ht_count=0;ht_count<=16;ht_count++){
        PeerAssoc a;a.vdevId=3;a.aid=21;a.legacyRateCount=rate_count;a.htRateCount=ht_count;a.qos=ht_count!=0;
        for(unsigned i=0;i<rate_count;i++)a.legacyRates[i]=uint8_t(12+2*i);
        for(unsigned i=0;i<ht_count;i++)a.htRates[i]=uint8_t(i);
        std::memcpy(a.peer,own,6);
        const auto n=assocBuildPeerAssoc(w,bytes,sizeof(bytes),a);
        const uint8_t *p=bytes+4;uint32_t left=n-4;
        auto fixed=next(p,left,0x65,248);assert(!std::memcmp(fixed.value,own,6));
        assert(wmiGet(fixed.value,2)==3&&wmiGet(fixed.value,4)==21&&wmiGet(fixed.value,61)==0);
        assert(wmiGet(fixed.value,5)&kWmiPeerFlagNeedPtk4Way);assert(!(wmiGet(fixed.value,5)&kWmiPeerFlagAuth));
        auto rates=next(p,left,17,(rate_count+3)&~3u);assert(!std::memcmp(rates.value,a.legacyRates,rate_count));
        auto ht=next(p,left,17,(ht_count+3)&~3u);assert(!std::memcmp(ht.value,a.htRates,ht_count));
        next(p,left,0x66,20);next(p,left,18,0);
        auto mlo=next(p,left,18,68);assert(wmiGet(mlo.value,0)==0x03d00040);zero(mlo.value+4,64);
        next(p,left,18,0);next(p,left,18,0);next(p,left,18,0);assert(!left);cases++;
        assert(n==376+((rate_count+3)&~3u)+((ht_count+3)&~3u));
        for(unsigned cap=0;cap<n;cap++){assert(!assocBuildPeerAssoc(w,bytes,cap,a));cases++;}
    }
    // Authenticating wire alone does not turn the controlled port into UP.
    assert(cases>100000);
    return 0;
}
