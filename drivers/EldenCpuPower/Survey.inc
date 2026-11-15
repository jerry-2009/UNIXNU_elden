/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Included inside CpuPerfSurvey's namespace. No level/limit/PSCI writes. */
static bool powerReady(void){
    return elden_recovery_armed()&&!native_owner_data_status&&elden_init_exec_accepted&&
        elden_pd_power_observation()==EldenPdReady;
}
static bool sampleLoads(EldenCpuTicks out[8]){
    bool all=true;
    for(unsigned cpu=0;cpu<8;++cpu){
        out[cpu]={};processor_t p=cpu_to_processor((int)cpu);
        processor_basic_info_data_t basic={};processor_cpu_load_info_data_t load={};
        host_t host=nullptr;mach_msg_type_number_t count=PROCESSOR_BASIC_INFO_COUNT;
        if(!p||processor_info(p,PROCESSOR_BASIC_INFO,&host,(processor_info_t)&basic,&count)!=KERN_SUCCESS||
           count!=PROCESSOR_BASIC_INFO_COUNT||!basic.running||basic.slot_num!=(int)cpu){all=false;continue;}
        count=PROCESSOR_CPU_LOAD_INFO_COUNT;
        if(processor_info(p,PROCESSOR_CPU_LOAD_INFO,&host,(processor_info_t)&load,&count)!=KERN_SUCCESS||
           count!=PROCESSOR_CPU_LOAD_INFO_COUNT){all=false;continue;}
        out[cpu].at=mach_absolute_time();out[cpu].valid=true;
        for(unsigned i=0;i<4;++i)out[cpu].ticks[i]=load.cpu_ticks[i];
    }
    return all;
}
static bool powerWait(unsigned milliseconds){
    for(unsigned elapsed=0;elapsed<milliseconds;elapsed+=100){
        if(!powerReady())return false;IOSleep(100);
    }
    return powerReady();
}
static void powerObservation(void){
    EldenCpuTicks previous[8]={},current[8]={};unsigned wait;
    for(wait=0;wait<2400;++wait){
        if(powerReady()&&sampleLoads(previous))break;
        IOSleep(100);
    }
    if(wait==2400||!powerWait(30000)){
        report("\nELDEN_CPU_POWER refused ready/online/settle; no SCMI\n");return;
    }
    uint32_t empty=0;
    if(!__atomic_compare_exchange_n(&sm8750_cpucp_owner,&empty,0x45504350u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        report("\nELDEN_CPU_POWER refused owner=%x\n",empty);return;
    }
    bool good=map(tx,ELDEN_CPUCP_TX_BASE,ELDEN_CPUCP_TX_BYTES)&&map(shared,ELDEN_CPUCP_SCMI_BASE,ELDEN_CPUCP_SCMI_BYTES);
    bool complete=true,enabled[2]={true,true};unsigned intervals=0;
    uint64_t hz=counterFrequency(),tick=hz_tick_interval;
    if(good)good=hz>=1000000&&hz<=100000000&&tick&&tick<=hz/50;
    if(good){
        perf.channel.io={nullptr,read,write,ring,counter,pause,nullptr,hz,30,allowMessage};
        perf.channel.sequence=scmi::headerToken(read(nullptr,scmi::kHeader));
        good=powerReady()&&show("power-describe",scmi::probe(&perf));
        if(good){
            report("\nELDEN_CPU_POWER begin cpus=8 domains=%u hz=%llu tick=%llu base=%x perf=%x PERF_SET=0 LIMITS_SET=0\n",
                perf.domains,hz,tick,perf.baseVersion,perf.perfVersion);
            for(unsigned d=0;d<2;++d){
                const scmi::Domain &domain=perf.domain[d];
                report("\nELDEN_CPU_POWER domain=%u name=%s flags=%x levels=%u\n",d,domain.name,domain.flags,domain.count);
                for(unsigned i=0;i<domain.count;++i)report("\nELDEN_CPU_LEVEL domain=%u index=%u raw=%u khz=%u latency-us=%u\n",
                    d,i,domain.levels[i].value,domain.levels[i].khz,domain.levels[i].latencyUs);
            }
            for(unsigned sample=0;sample<9&&good;++sample){
                if(sample&&!powerWait(3000)){good=false;break;}
                if(!powerReady()||!sampleLoads(current)){good=false;break;}
                for(unsigned cpu=0;cpu<8;++cpu){
                    const EldenCpuLoad load=elden_cpu_load(previous[cpu],current[cpu],tick);
                    uint64_t dt=current[cpu].at-previous[cpu].at;
                    bool valid=sample&&load.valid&&dt<=10*hz;
                    report("\nELDEN_CPU_LOAD sample=%u cpu=%u at=%llu ticks=%u,%u,%u,%u valid=%u busy-pm=%u delta=%llu idle=%llu\n",
                        sample,cpu,current[cpu].at,current[cpu].ticks[0],current[cpu].ticks[1],current[cpu].ticks[2],current[cpu].ticks[3],
                        valid?1u:0u,valid?load.busy_pm:0u,load.total,load.idle);
                    if(sample&&!valid)complete=false;
                    previous[cpu]=current[cpu];
                }
                for(unsigned d=0;d<2;++d){
                    if(!enabled[d])continue;
                    if(!powerReady()){good=false;break;}
                    uint32_t index=0,raw=0;scmi::Result result=scmi::levelGet(&perf,d,&index,&raw);
                    if(!scmi::ok(result)){
                        complete=false;
                        report("\nELDEN_CPU_POWER level-error sample=%u domain=%u error=%u status=%d\n",sample,d,(unsigned)result.error,result.status);
                        /* A completed, explicit protocol rejection disables this
                         * domain only, never converting partial data to success.
                         * Transport/malformed/unknown-level errors stop all I/O. */
                        if(result.error==scmi::kStatus&&(result.status==-1||result.status==-2||result.status==-3))enabled[d]=false;
                        else {good=false;break;}
                    }else report("\nELDEN_CPU_CURRENT sample=%u domain=%u raw=%u index=%u table-khz=%u exact=%u\n",
                        sample,d,raw,index,perf.domain[d].levels[index].khz,perf.domain[d].levels[index].value==raw?1u:0u);
                }
                if(sample)++intervals;
            }
        }
    }
    bool free=shared.address&&(read(nullptr,scmi::kChannelStatus)&scmi::kChannelFree);
    report("\nELDEN_CPU_POWER end ok=%u complete=%u intervals=%u domains=%u,%u channel-free=%u access-error=%u transfers=%llu; levels unchanged\n",
        good?1u:0u,good&&complete&&intervals==8?1u:0u,intervals,enabled[0]?1u:0u,enabled[1]?1u:0u,free?1u:0u,malformed_access?1u:0u,perf.channel.transfers);
    if(!perf.channel.transfers||free){unmap(shared);unmap(tx);__atomic_store_n(&sm8750_cpucp_owner,0,__ATOMIC_RELEASE);}
}
