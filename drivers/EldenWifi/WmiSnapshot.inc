/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" void elden_wifi_irq_snapshot(uint32_t,uint32_t [10]);
static unsigned wmi_snapshot_done;
static bool runtime_wmi_timeout_line(const char *line){
    if(!line)return false;
    size_t n=0;while(n<128&&line[n])n++;if(n==128)return false;
    while(n&&(line[n-1]=='\n'||line[n-1]=='\r'))n--;
    return n>=21&&!strncmp(line,"wmi command ",12)&&!memcmp(line+n-8," timeout",8);
}
static void runtime_wmi_snapshot(Context *c,const char *line){
    if(!c||!runtime_wmi_timeout_line(line)||
       !c->runtime_entered||c->runtime_returned||c->transport_cleanup||
       __atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE))return;
    if(__atomic_exchange_n(&wmi_snapshot_done,1u,__ATOMIC_ACQ_REL))return;
    uint32_t s[10]={};elden_wifi_irq_snapshot((uint32_t)c->runtime_board.irq_base,s);
    uint64_t daif=0,mpidr=0;__asm__ volatile("mrs %0,daif":"=r"(daif));__asm__ volatile("mrs %0,mpidr_el1":"=r"(mpidr));
    uint32_t hardware=UINT32_MAX,enable=UINT32_MAX,mask=UINT32_MAX,mhi=UINT32_MAX;
    int admitted=transport_admit(c,false),rs=admitted,re=admitted,rm=admitted,rh=admitted;
    if(!admitted){
        rs=c->maps[EldenPcieDbi].read(EldenMsiStatus,&hardware);
        re=c->maps[EldenPcieDbi].read(EldenMsiEnable,&enable);
        rm=c->maps[EldenPcieDbi].read(EldenMsiMask,&mask);
        rh=c->bar0_map.read(0x48,&mhi);
    }
    log("\nELDEN_WMI_IRQ used=%x enabled=%x pending=%x strict=%x disabled=%x running=%x depth=%u active=%u mutexes=%u polling=%u\n",
        s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7],s[8],s[9]);
    log("\nELDEN_WMI_NATIVE admit=%d HW=%x/%x/%x MHI=%x reads=%d/%d/%d/%d count=%u pending=%x error=%d inflight=%u state=%u DAIF=%llx MPIDR=%llx target=%llx\n",
        admitted,hardware,enable,mask,mhi,rs,re,rm,rh,__atomic_load_n(&c->msi.irq_count,__ATOMIC_RELAXED),
        __atomic_load_n(&c->msi.pending,__ATOMIC_ACQUIRE),__atomic_load_n(&c->msi.irq_error,__ATOMIC_ACQUIRE),
        __atomic_load_n(&c->msi.irq_calls,__ATOMIC_SEQ_CST),c->msi.state,(unsigned long long)daif,(unsigned long long)mpidr,(unsigned long long)c->msi.affinity);
}
