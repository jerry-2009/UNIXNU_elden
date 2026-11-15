/* SPDX-License-Identifier: GPL-2.0-only
 * DesignWare group0 method from fixed TB322FC Linux and Sheng. No ITS command
 * or other MSI group is touched. See MSI.md for the deliberate route change.
 */
#include "Msi.h"

static int irq_error(EldenPcieMsi *m){return __atomic_load_n(&m->irq_error,__ATOMIC_ACQUIRE);}
static int failure(EldenPcieMsi *m,int rc){
    if(!m->error)m->error=rc;
    if(m->attached)(void)m->io.mask_irq(m->io.context,EldenMsiIntid,true);
    m->state=m->controls_started?EldenMsiHeld:EldenMsiRefused;return rc;
}
static int admit(EldenPcieMsi *m){int rc=irq_error(m);return rc?rc:m->io.admit(m->io.context);}
static int write_check(EldenPcieMsi *m,uint32_t off,uint32_t value,bool starting){
    int rc=starting?admit(m):0;if(rc)return rc;
    m->controls_started=true;m->writes++;
    rc=m->io.write(m->io.context,off,value);if(rc)return rc;
    uint32_t readback=0;rc=m->io.read(m->io.context,off,&readback);if(rc)return rc;
    if(readback!=value)return -71;
    return starting?admit(m):0;
}
static void irq_fault(EldenPcieMsi *m,int rc){
    int expected=0;__atomic_compare_exchange_n(&m->irq_error,&expected,rc,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
    (void)m->io.mask_irq(m->io.context,EldenMsiIntid,true);
    m->io.wake(m->io.context);
}
static void interrupt(void *cookie){
    EldenPcieMsi *m=cookie;
    /* SC closes the admission-vs-inflight race: a stop observing zero after
     * withdrawal cannot miss a late handler that would still access DBI. */
    __atomic_add_fetch(&m->irq_calls,1u,__ATOMIC_SEQ_CST);
    if(!__atomic_load_n(&m->irq_access,__ATOMIC_SEQ_CST))goto done;
    uint32_t status=0;int rc=m->io.read(m->io.context,EldenMsiStatus,&status);
    if(rc){irq_fault(m,rc);goto done;}
    __atomic_add_fetch(&m->irq_count,1u,__ATOMIC_RELAXED);
    if(!status){
        if(__atomic_add_fetch(&m->empty_count,1u,__ATOMIC_RELAXED)>=128)irq_fault(m,-5);
        goto done;
    }
    __atomic_store_n(&m->empty_count,0u,__ATOMIC_RELAXED);
    /* Ack only the observed bits. A later arrival remains latched and can
     * assert the level line again; no unbounded IRQ polling or callbacks. */
    rc=m->io.write(m->io.context,EldenMsiStatus,status);
    if(rc){irq_fault(m,rc);goto done;}
    __atomic_fetch_or(&m->pending,status,__ATOMIC_RELEASE);
    m->io.wake(m->io.context);
done:
    __atomic_sub_fetch(&m->irq_calls,1u,__ATOMIC_SEQ_CST);
}
int elden_pcie_msi_prepare(EldenPcieMsi *m,uint64_t sink,uint64_t affinity){
    if(!m||!sink||sink>UINT32_MAX||(sink&4095))return -22;
    if(m->state!=EldenMsiIdle)return -16;
    if(!m->io.admit||!m->io.quiesced||!m->io.read||!m->io.write||!m->io.attach||!m->io.mask_irq||
       !m->io.wake||!m->io.now_us||!m->io.delay_us)return -22;
    m->state=EldenMsiWorking;m->stage=1;m->target=sink;m->affinity=affinity;
    int rc=admit(m);if(rc)return failure(m,rc);
    rc=m->io.quiesced(m->io.context);if(rc)return failure(m,rc);
    uint32_t enable=0,mask=0,status=0;
    if((rc=m->io.read(m->io.context,EldenMsiEnable,&enable))||
       (rc=m->io.read(m->io.context,EldenMsiMask,&mask)))return failure(m,rc);
    /* A running receiver is not ours. Do not silently steal its vectors. */
    if(enable&~mask)return failure(m,-16);
    m->stage=2;
    if((rc=write_check(m,EldenMsiMask,UINT32_MAX,true))||
       (rc=write_check(m,EldenMsiEnable,0,true)))return failure(m,rc);
    if((rc=m->io.read(m->io.context,EldenMsiStatus,&status)))return failure(m,rc);
    if(status){
        if((rc=admit(m)))return failure(m,rc);
        m->writes++;rc=m->io.write(m->io.context,EldenMsiStatus,status);if(rc)return failure(m,rc);
        if((rc=m->io.read(m->io.context,EldenMsiStatus,&status)))return failure(m,rc);
        if(status)return failure(m,-71);
    }
    m->stage=3;
    if((rc=write_check(m,EldenMsiAddrLo,(uint32_t)sink,true))||
       (rc=write_check(m,EldenMsiAddrHi,0,true)))return failure(m,rc);
    m->stage=4;uint32_t flags=0;uint64_t router=0;
    __atomic_store_n(&m->irq_access,1u,__ATOMIC_SEQ_CST);
    rc=m->io.attach(m->io.context,EldenMsiIntid,interrupt,m,&flags,&router);
    if(rc){__atomic_store_n(&m->irq_access,0u,__ATOMIC_SEQ_CST);return failure(m,rc);}
    m->attached=true;
    rc=m->io.mask_irq(m->io.context,EldenMsiIntid,true);if(rc)return failure(m,rc);
    if(flags!=0xa003||router!=affinity)return failure(m,-71);
    if((rc=admit(m)))return failure(m,rc);
    m->state=EldenMsiPrepared;m->stage=5;return 0;
}
int elden_pcie_msi_arm(EldenPcieMsi *m){
    if(!m||m->state!=EldenMsiPrepared||!m->attached)return -22;
    int rc=admit(m);if(rc)return failure(m,rc);
    m->stage=6;
    if((rc=write_check(m,EldenMsiEnable,UINT32_MAX,true)))return failure(m,rc);
    rc=m->io.mask_irq(m->io.context,EldenMsiIntid,false);if(rc)return failure(m,rc);
    if((rc=write_check(m,EldenMsiMask,0,true)))return failure(m,rc);
    m->stage=7;m->state=EldenMsiArmed;return 0;
}
uint32_t elden_pcie_msi_pending(EldenPcieMsi *m){return m?__atomic_exchange_n(&m->pending,0u,__ATOMIC_ACQ_REL):0;}
int elden_pcie_msi_stop(EldenPcieMsi *m,uint64_t deadline){
    if(!m||m->state==EldenMsiIdle||m->state==EldenMsiWorking)return -22;
    if(m->state==EldenMsiStopped)return 0;
    if(m->stop_attempted)return m->stop_result;
    if(m->io.now_us(m->io.context)>=deadline)return -110;
    /* Keep receiving the completion needed by MHI until the caller actually
     * proves its engines drained. A premature request changes no controls. */
    int rc=m->io.quiesced(m->io.context);if(rc)return rc;
    m->stop_attempted=true;m->stage=8;
    __atomic_store_n(&m->irq_access,0u,__ATOMIC_SEQ_CST);
    int first=0;
    if(m->attached)first=m->io.mask_irq(m->io.context,EldenMsiIntid,true);
    if(m->controls_started){
        rc=write_check(m,EldenMsiMask,UINT32_MAX,false);if(!first&&rc)first=rc;
        rc=write_check(m,EldenMsiEnable,0,false);if(!first&&rc)first=rc;
    }
    uint64_t before=m->io.now_us(m->io.context);
    for(unsigned wait=0;__atomic_load_n(&m->irq_calls,__ATOMIC_SEQ_CST);wait++){
        uint64_t now=m->io.now_us(m->io.context);
        if(now<before||now>=deadline||wait>=1000){if(!first)first=-110;break;}
        m->io.delay_us(m->io.context,10);
    }
    if(m->io.now_us(m->io.context)>=deadline&&!first)first=-110;
    m->stop_result=first;
    if(first)return failure(m,first);
    m->stage=9;m->state=EldenMsiStopped;return 0;
}
