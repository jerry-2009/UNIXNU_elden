/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "EldenCpuFreqPolicy.h"
#include "CpuPerfAccess.h"

/* Single-writer controller. The caller owns the CPUCP channel and supplies
 * atomic stop/readiness requests; it never calls this concurrently. No limits,
 * voltage, suspend, retry or forced channel-clear operation is permitted. */
namespace elden_cpufreq {
enum Phase {Cold, Running, Confirming, Restoring, Stopped, Held, Refused};
enum Failure {None, Configuration, Probe, Capabilities, Readback, Transport,
    Rejected, ConfirmationTimeout, ReadinessLost, InvalidWindow, Clock,FirmwareError};
struct Config {uint32_t capKhz[2];bool bootCeiling;};
struct Input {
    bool ready,stop;
    uint32_t touches;
    cpufreq::CpuWindow cpu[8];
};
struct Control {
    scmi::Perf perf;
    cpufreq::Governor governor;
    Phase phase;
    Failure failure;
    scmi::Result error;
    uint32_t original[2],ceiling[2],requested[2];
    bool dirty[2],restoreAttempted[2],permitSet,stopping;
    uint32_t pendingDomain,pendingTarget,observed,nextDomain;
    bool pendingRestore;
    uint64_t pendingDeadline,nextRead,nextSet[2],lastNow,minimumWindow;
    uint32_t sets,confirmations,restoreSets,restoreConfirmed,windows;
};

static inline bool allowed(const Control *c,uint32_t protocol,uint32_t message){
    return elden_cpu_perf_query(protocol,message)||
        (c&&c->permitSet&&protocol==scmi::kPerf&&message==scmi::kLevelSet);
}
static inline uint64_t now(const Control *c){return c->perf.channel.io.now(c->perf.channel.io.context);}
static inline bool terminal(const Control *c){return c->phase==Stopped||c->phase==Held||c->phase==Refused;}
static inline void fail(Control *c,Failure failure,scmi::Result result={}){
    if(c->failure==None){c->failure=failure;c->error=result;}
    c->stopping=true;
}
static inline bool initialize(Control *c,const scmi::Io &io,const Config &cfg,bool ready){
    if(c->phase!=Cold)return false;
    if(!ready||!io.now||!io.allowed||!io.allowMessage||!io.read32||!io.write32||!io.ring||
       io.hz<1000000||io.hz>100000000||!io.timeoutMs||io.timeoutMs>30){
        c->phase=Refused;fail(c,Configuration);return false;
    }
    c->perf.channel.io=io;c->lastNow=now(c);c->minimumWindow=cpufreq::ticks(io.hz,20);
    c->perf.channel.sequence=scmi::headerToken(io.read32(io.context,scmi::kHeader));
    scmi::Result r=scmi::probe(&c->perf);
    if(!scmi::ok(r)){c->phase=Refused;fail(c,Probe,r);return false;}
    if(c->perf.domains!=2){c->phase=Refused;fail(c,Capabilities);return false;}
    for(unsigned d=0;d<2;++d){
        const scmi::Domain &domain=c->perf.domain[d];
        if(!(domain.flags&scmi::kCanSetLevel)||domain.count<1||domain.rateLimitUs>500000||
           !cfg.capKhz[d]||cfg.capKhz[d]>domain.sustainedKhz||cfg.capKhz[d]<domain.levels[0].khz){
            c->phase=Refused;fail(c,Capabilities);return false;
        }
        for(unsigned i=0;i<domain.count;++i){
            bool valid=domain.levels[i].khz&&(!i||domain.levels[i-1].khz<domain.levels[i].khz);
            for(unsigned j=0;j<i;++j)if(domain.levels[i].value==domain.levels[j].value)valid=false;
            if(!valid){c->phase=Refused;fail(c,Capabilities);return false;}
        }
        uint32_t raw=0;r=scmi::levelGet(&c->perf,d,&c->original[d],&raw);
        if(!scmi::ok(r)||domain.levels[c->original[d]].value!=raw){
            c->phase=Refused;fail(c,Readback,r);return false;
        }
        c->ceiling[d]=cpufreq::capIndex(domain,cfg.capKhz[d]);
        if(cfg.bootCeiling&&c->ceiling[d]>c->original[d])c->ceiling[d]=c->original[d];
        c->requested[d]=c->original[d];
    }
    cpufreq::governorInit(&c->governor,c->perf,0,c->original,io.hz,now(c));
    c->governor.launchMs=0; // No invented app-exec, GPU or screen-state input.
    for(unsigned d=0;d<2;++d){
        cpufreq::Domain &domain=c->governor.domain[d];unsigned cap=c->ceiling[d];
        domain.top=cap;domain.count=cap+1;
        domain.floor=cpufreq::clip(domain.floor,cap);domain.touch=cpufreq::clip(domain.touch,cap);
        domain.gpu=cpufreq::clip(domain.gpu,cap);domain.launch=cpufreq::clip(domain.launch,cap);
        domain.cap=cpufreq::clip(domain.cap,cap);domain.offCap=cpufreq::clip(domain.offCap,cap);
    }
    c->lastNow=now(c);c->phase=Running;return true;
}

/* An acknowledged SET is still pending: Linux's scmi-cpufreq documents that
 * the OPP transition is asynchronous. Only an exact later GET confirms it. */
static inline bool request(Control *c,unsigned d,unsigned target,bool restore){
    if((restore?c->phase!=Restoring:c->phase!=Running)||d>=2||target>=c->perf.domain[d].count||
       (!restore&&(c->stopping||target>c->ceiling[d]))||
       (restore&&(target!=c->original[d]||c->restoreAttempted[d]))){
        fail(c,Configuration);c->phase=Held;return false;
    }
    if(now(c)<c->nextSet[d])return false;
    if(restore)c->restoreAttempted[d]=true;
    bool wasDirty=c->dirty[d];c->dirty[d]=true;c->permitSet=true;
    scmi::Result result=scmi::levelSet(&c->perf,d,target);
    c->permitSet=false;
    ++c->sets;if(restore)++c->restoreSets;
    uint64_t at=now(c),rate=(uint64_t)c->perf.domain[d].rateLimitUs*c->perf.channel.io.hz/1000000;
    c->nextSet[d]=at+rate;
    if(!scmi::ok(result)){
        // NOT_SUPPORTED/INVALID/DENIED/NOT_FOUND/OUT_OF_RANGE/BUSY explicitly
        // reject this request. COMMS/GENERIC/HARDWARE/PROTOCOL errors cannot
        // establish that the clock stayed unchanged, even with a reply.
        bool noExecution=result.error==scmi::kStatus&&result.status>=-6&&result.status<=-1;
        fail(c,noExecution?Rejected:result.error==scmi::kStatus?FirmwareError:Transport,result);
        if(noExecution&&!restore){c->dirty[d]=wasDirty;c->phase=Restoring;}
        else c->phase=Held; // Uncertain/failed restore: no further I/O.
        return false;
    }
    c->pendingDomain=d;c->pendingTarget=target;c->pendingRestore=restore;c->observed=UINT32_MAX;
    c->pendingDeadline=at+cpufreq::ticks(c->perf.channel.io.hz,1000);
    c->nextRead=at+c->minimumWindow;c->phase=Confirming;return true;
}
static inline void restoreNext(Control *c){
    c->phase=Restoring;
    for(int d=1;d>=0;--d)if(c->dirty[d]){
        if(c->restoreAttempted[d]){c->phase=Held;return;}
        request(c,(unsigned)d,c->original[d],true);return;
    }
    c->phase=Stopped;
}
static inline void confirm(Control *c){
    uint64_t at=now(c);if(at<c->nextRead)return;
    if(at>c->pendingDeadline){
        fail(c,ConfirmationTimeout);c->phase=Held;
        return;
    }
    uint32_t index=0,raw=0;scmi::Result r=scmi::levelGet(&c->perf,c->pendingDomain,&index,&raw);
    c->nextRead=now(c)+c->minimumWindow;
    if(!scmi::ok(r)){
        fail(c,Readback,r);c->phase=Held;return;
    }
    c->observed=index;
    if(now(c)>c->pendingDeadline){
        fail(c,ConfirmationTimeout);c->phase=Held;
    }else if(index==c->pendingTarget){
        unsigned d=c->pendingDomain;cpufreq::governorSet(&c->governor,d,index,now(c));c->requested[d]=index;
        if(c->pendingRestore){c->dirty[d]=false;++c->restoreConfirmed;}
        else {++c->confirmations;c->nextDomain=1u-d;}
        if(c->stopping)restoreNext(c);else c->phase=Running;
    }else if(now(c)>=c->pendingDeadline){
        // Never call a lower firmware level a successful requested setting and
        // never repeatedly reassert a vote against a possible thermal limit.
        fail(c,ConfirmationTimeout);
        c->phase=Held;
    }
}
static inline void step(Control *c,const Input &input){
    if(terminal(c)||c->phase==Cold)return;
    uint64_t at=now(c);
    if(at<c->lastNow){fail(c,Clock);c->phase=Held;return;}
    if(at-c->lastNow< c->minimumWindow&&!input.stop&&!c->stopping&&input.ready)return;
    c->lastNow=at;
    if(input.stop)c->stopping=true;
    if(!input.ready)fail(c,ReadinessLost);
    if(c->phase==Confirming){confirm(c);return;}
    if(c->stopping||c->phase==Restoring){restoreNext(c);return;}
    for(unsigned cpu=0;cpu<8;++cpu){
        const cpufreq::CpuWindow &w=input.cpu[cpu];
        if(w.domain!=(cpu<6?0u:1u)||!w.span||w.busy>w.span||w.span>c->perf.channel.io.hz){
            fail(c,InvalidWindow);restoreNext(c);return;
        }
    }
    uint32_t target[2]={};
    cpufreq::governorStep(&c->governor,at,input.cpu,8,input.touches,0,0,target);
    ++c->windows;
    for(unsigned slot=0;slot<2;++slot){unsigned d=(c->nextDomain+slot)%2;
      if(target[d]!=c->governor.domain[d].level){
        request(c,d,target[d],false);break;
      }
    }
}
} // namespace elden_cpufreq
