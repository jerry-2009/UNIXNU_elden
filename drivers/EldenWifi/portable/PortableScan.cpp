/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * CE/HTC/WMI/HTT implementation: Leo Zhang, upstream source.json. The only
 * device adaptation here is ownership, existing NC/IOVA memory, factory MAC,
 * and a scan-only lifetime. No Piano PMIC/PCIe/SMMU or macOS ABI is imported.
 */
#include "PortableApi.h"
#include "upstream/WifiLink.h"

namespace {
using namespace pianowifi;
/* Large upstream state lives in BSS, never as a fresh Link/HttRx on XNU's
 * kernel stack. One lifetime per boot; retained until physical reset. */
static Ce ce;
static HttRx htt;
static Link link;
static Arena arena;
static EldenPortableIo owner_io;
static unsigned used,stopping,disabled;

static void status(EldenPortableStatus *s) {
    if(!s)return;
    *s={link.step,link.error,(uint32_t)link.ready.seen,link.commands,link.events,
        link.htc.creditReports,link.creditWaits,link.round+1,(uint32_t)link.scanStarted,
        (uint32_t)link.scanCompleted,link.scan.count,link.mgmtFrames,ce.sent,ce.received,
        ce.completions,ce.dropped,htt.announced};
}
}
extern "C" int elden_wifi_portable_requested(void) {
#if defined(ELDEN_WIFI_PORTABLE_SCAN_TRIAL) && ELDEN_WIFI_PORTABLE_SCAN_TRIAL==1
    return 1;
#else
    return 0;
#endif
}
extern "C" int elden_wifi_portable_prepare(const EldenPortableIo *io,void *cpu,
    uint64_t bus,uint32_t bytes,const uint8_t *mac,uint64_t now_ms) {
    if(!elden_wifi_portable_requested())return -95;
    if(used)return -16;
    if(!io||!io->owner||!io->read||!io->write||!cpu||!mac||
       bytes!=(4u<<20)||((uintptr_t)cpu&4095)||!bus||(bus&(bytes-1))||
       bus>UINT32_MAX-(uint64_t)bytes+1||!wmiMacUsable(mac))return -22;
    used=1;owner_io=*io;
    arenaInit(arena,(uint8_t *)cpu,bus,bytes);
    if(!cePlan(ce,arena,kCePipeMaskWithHtt)||!httPlan(htt,arena,true))return -12;
    httFill(htt);
    const ChipIo chip{io->owner,io->read,io->write};
    ceProgram(ce,chip);
    LinkOptions options;
    options.htt=&htt;
    options.handOff=true;
    options.ownMacSet=true;
    for(unsigned i=0;i<6;i++)options.ownMac[i]=mac[i];
    /* The donor's successful two-round receive-buffer scan, including actual
     * credit reports and regulatory channel selection. Its supported mode1
     * and packet codecs are intact; no success is synthesized on timeout. */
    link.note=io->note;link.noteCtx=io->owner;
    linkBegin(link,ce,chip,options,now_ms);
    return 0;
}
extern "C" int elden_wifi_portable_tick(void *owner,uint64_t now_ms,EldenPortableStatus *s) {
    if(!used||owner!=owner_io.owner||disabled)return -19;
    if(stopping)return -108;
    (void)linkRun(link,now_ms);status(s);
    /* The donor returns its negative error on the transition to Stopped,
     * whereas subsequent turns return the state number. Check saved state. */
    if(link.step==kLinkStopped)return link.error?link.error:-5;
    return 0;
}
extern "C" int elden_wifi_portable_stop_tick(void *owner,uint64_t now_ms) {
    if(!used||owner!=owner_io.owner||disabled)return -19;
    stopping=1;
    return linkStopRequest(link,now_ms)?1:0;
}
extern "C" void elden_wifi_portable_disable(void *owner) {
    if(!used||owner!=owner_io.owner||disabled)return;
    stopping=1;linkDisable(link);disabled=1;
    /* Both DMA backing and protocol state remain retained until reset. */
}
