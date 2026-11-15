/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Single worker owns the controller and mappings. Only finalRun is observed
 * by the recovery callback; no concurrent reads of mutable Control fields. */
static elden_cpufreq::Control governorControl;
static volatile unsigned governorStop,governorRun; // 0 not started,1 active,2 clean,3 held
static bool governorReady(uint32_t expectedEpoch,uint32_t *epoch=nullptr){
    if(__atomic_load_n(&governorStop,__ATOMIC_ACQUIRE)||!elden_recovery_rpc_ready()||
       elden_recovery_deadline_remaining()<15||!powerReady()||!elden_charge_policy_ready())return false;
    int temperature=0;uint32_t e=0,cycle=0;
    if(!elden_battery_temperature_get(&temperature,&e,&cycle)||!e||!cycle||
       temperature<500||temperature>4000||(expectedEpoch&&expectedEpoch!=e))return false;
    if(epoch)*epoch=e;return true;
}
static bool governorThreadAllowed(void *){return !ml_at_interrupt_context();}
static bool governorMessage(void *,uint32_t protocol,uint32_t message){
    if(protocol==scmi::kPerf&&message==scmi::kLevelSet&&
       __atomic_load_n(&governorStop,__ATOMIC_ACQUIRE)&&governorControl.phase!=elden_cpufreq::Restoring)return false;
    return elden_cpufreq::allowed(&governorControl,protocol,message);
}
static bool governorSleep(unsigned ms,uint32_t epoch){
    for(unsigned waited=0;waited<ms;waited+=20){
        if(!governorReady(epoch))return false;IOSleep(20);
    }
    return governorReady(epoch);
}
static bool governorWindows(const EldenCpuTicks before[8],const EldenCpuTicks after[8],
                            uint64_t hz,uint64_t tick,cpufreq::CpuWindow out[8]){
    if(!tick||tick>hz/50)return false;
    for(unsigned cpu=0;cpu<8;++cpu){
        if(!before[cpu].valid||!after[cpu].valid||after[cpu].at<=before[cpu].at)return false;
        uint64_t span=after[cpu].at-before[cpu].at,total=0;
        for(unsigned n=0;n<4;++n)total+=(uint32_t)(after[cpu].ticks[n]-before[cpu].ticks[n]);
        uint64_t expected=span/tick;
        if(span>hz||span<tick||total+3<expected||total>expected+3)return false;
        cpufreq::CpuTicks a={true,true,cpu<6?0u:1u,before[cpu].ticks[2]};
        cpufreq::CpuTicks b={true,true,cpu<6?0u:1u,after[cpu].ticks[2]};uint32_t online[2]={};
        cpufreq::cpuWindows(&b,&a,1,span,tick,&out[cpu],online);
        if(online[cpu<6?0:1]!=1)return false;
    }
    return true;
}
static void governorReport(const char *phase,uint64_t started,uint64_t hz){
    const auto &c=governorControl;
    report("\nELDEN_CPU_GOV phase=%s elapsed-ms=%llu state=%u error=%u scmi=%u/%d windows=%u sets=%u confirmed=%u restore=%u/%u levels=%u,%u table-khz=%u,%u caps=%u,%u\n",
        phase,(counter(nullptr)-started)/(hz/1000),(unsigned)c.phase,(unsigned)c.failure,
        (unsigned)c.error.error,c.error.status,c.windows,c.sets,c.confirmations,c.restoreConfirmed,c.restoreSets,
        c.governor.domain[0].level,c.governor.domain[1].level,
        c.governor.domain[0].khz[c.governor.domain[0].level],c.governor.domain[1].khz[c.governor.domain[1].level],c.ceiling[0],c.ceiling[1]);
}
static void governorWorker(void){
    unsigned idle=0;
    if(!__atomic_compare_exchange_n(&governorRun,&idle,1u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    bool owned=false,clean=true;uint32_t epoch=0;EldenCpuTicks previous[8]={},current[8]={};
    unsigned wait=0;
    for(;wait<2400&&!__atomic_load_n(&governorStop,__ATOMIC_ACQUIRE);++wait){
        if(governorReady(0,&epoch)&&elden_recovery_deadline_remaining()>=180&&sampleLoads(previous))break;
        IOSleep(100);
    }
    if(wait==2400||!governorReady(epoch)){report("\nELDEN_CPU_GOV refused startup gate; no SCMI\n");goto done;}
    report("\nELDEN_CPU_GOV phase=baseline seconds=30 epoch=%u; no SET\n",epoch);
    if(!governorSleep(30000,epoch)){report("\nELDEN_CPU_GOV refused baseline; no SCMI\n");goto done;}
    {
        uint32_t empty=0;
        if(!__atomic_compare_exchange_n(&sm8750_cpucp_owner,&empty,0x45504350u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
            report("\nELDEN_CPU_GOV refused owner=%x\n",empty);goto done;
        }
        owned=true;
    }
    if(!map(tx,ELDEN_CPUCP_TX_BASE,ELDEN_CPUCP_TX_BYTES)||!map(shared,ELDEN_CPUCP_SCMI_BASE,ELDEN_CPUCP_SCMI_BYTES)){
        report("\nELDEN_CPU_GOV refused mapping\n");goto release;
    }
    {
        uint64_t hz=counterFrequency(),tick=hz_tick_interval;
        if(hz!=19200000||!tick||tick>hz/50){report("\nELDEN_CPU_GOV refused timebase\n");goto release;}
        scmi::Io io={nullptr,read,write,ring,counter,pause,governorThreadAllowed,hz,30,governorMessage};
        const elden_cpufreq::Config config={{3532800,4089600},true};
        bool initialized=elden_cpufreq::initialize(&governorControl,io,config,governorReady(epoch));
        uint64_t started=counter(nullptr),printed=started;uint32_t touch=0;
        governorReport(initialized?"active":"refused",started,hz);
        if(initialized){
            bool sampled=sampleLoads(previous);unsigned drains=0;
            while(!elden_cpufreq::terminal(&governorControl)){
                IOSleep(20);uint64_t at=counter(nullptr);
                elden_cpufreq::Input input={};
                input.ready=governorReady(epoch);
                input.stop=__atomic_load_n(&governorStop,__ATOMIC_ACQUIRE)||at-started>=90*hz||!sampled;
                uint32_t seq=__atomic_load_n(&native_touch_seq,__ATOMIC_ACQUIRE);
                if(!(seq&1))touch=seq;input.touches=touch;
                if(!sampleLoads(current)||!governorWindows(previous,current,hz,tick,input.cpu)){
                    elden_cpufreq::fail(&governorControl,elden_cpufreq::InvalidWindow);input.stop=true;
                }
                for(unsigned cpu=0;cpu<8;++cpu)previous[cpu]=current[cpu];
                if(input.stop||!input.ready||governorControl.stopping){
                    if(++drains>200){elden_cpufreq::fail(&governorControl,elden_cpufreq::ConfirmationTimeout);governorControl.phase=elden_cpufreq::Held;report("\nELDEN_CPU_GOV drain budget expired\n");break;}
                }
                elden_cpufreq::step(&governorControl,input);
                if(at-printed>=5*hz){governorReport("running",started,hz);printed=at;}
            }
        }
        governorReport("end",started,hz);
        clean=governorControl.phase==elden_cpufreq::Stopped||(!governorControl.sets&&governorControl.phase==elden_cpufreq::Refused);
    }
release:
    {
        bool free=clean&&(!governorControl.perf.channel.transfers||(shared.address&&(read(nullptr,scmi::kChannelStatus)&scmi::kChannelFree)));
        clean=clean&&free;
        if(clean){unmap(shared);unmap(tx);__atomic_store_n(&sm8750_cpucp_owner,0u,__ATOMIC_RELEASE);owned=false;}
        report("\nELDEN_CPU_GOV release clean=%u held=%u transfers=%llu\n",clean?1u:0u,owned?1u:0u,governorControl.perf.channel.transfers);
    }
done:
    __atomic_store_n(&governorRun,clean&&!owned?2u:3u,__ATOMIC_RELEASE);
}
