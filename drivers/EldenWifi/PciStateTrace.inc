/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Explicit passive trial. The existing MMIO callback records selected writes
 * into bounded RAM; it neither adds nor suppresses a device write. */
struct elden_pci_write_note { u32 offset,value,window; };
static struct {
    struct ath12k_base *owner;
    struct elden_pci_write_note writes[32];
    unsigned count,overflow,states,dumped;
    bool installed;
} elden_pci_state;

static void elden_pci_state_mmio(volatile void *address,u32 value)
{
    struct ath12k_base *ab=elden_pci_state.owner;
    unsigned long base,at;
    u32 off,window;
    unsigned slot;
    if(!ab||!ab->mem)return;
    base=(unsigned long)ab->mem;at=(unsigned long)address;
    if(at<base||at-base>ab->mem_len||ab->mem_len-(at-base)<sizeof(u32))return;
    off=(u32)(at-base);
    if(off!=0x3004U&&off!=0x3008U&&off!=0x38U&&
       off!=0x86000U&&off!=0x86004U&&off!=0x86008U&&off!=0x86010U)return;
    window=ioread32(ab->mem+0x3278U);
    if(off>=0x86000U&&(window&0x3fU)!=0x37U)return;
    slot=elden_pci_state.count++;
    if(slot>=32){elden_pci_state.overflow++;return;}
    elden_pci_state.writes[slot]=(struct elden_pci_write_note){off,value,window};
}

static void elden_pci_state_install(struct ath12k_base *ab)
{
    void (*expected)(volatile void *,u32)=NULL;
    if(!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||!ab->mem||ab->mem_len<0x86014U||
       elden_umac_owner!=ab||!elden_umac_device)return;
    if(elden_pci_state.owner)return;
    elden_pci_state.owner=ab;
    if(!__atomic_compare_exchange_n(&lx_mmio_trace,&expected,elden_pci_state_mmio,
            false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        elden_pci_state.owner=NULL;
        ath12k_warn(ab,"ELDEN_PCI_STATE refused existing-mmio-observer=1\n");
        return;
    }
    elden_pci_state.installed=true;
    ath12k_warn(ab,"ELDEN_PCI_STATE installed=1 writes-max=32 no-new-mmio-writes=1\n");
}

static void elden_pci_state_dump(struct ath12k_base *ab)
{
    unsigned i,count;
    if(elden_pci_state.owner!=ab||elden_pci_state.dumped)return;
    elden_pci_state.dumped=1;count=elden_pci_state.count;
    ath12k_warn(ab,"ELDEN_PCI_STATE_WRITES recorded=%u overflow=%u; CPU-callback-path-only\n",
        count<32?count:32,elden_pci_state.overflow);
    for(i=0;i<count&&i<32;i++){
        struct elden_pci_write_note *n=&elden_pci_state.writes[i];
        ath12k_warn(ab,"ELDEN_PCI_STATE_WRITE index=%u off=%x value=%x window=%x\n",
            i,n->offset,n->value,n->window);
    }
}

static void elden_pci_state_read(struct ath12k_base *ab,u32 requested,u32 observed)
{
    struct ath12k_pci *pci;
    struct mhi_controller *mhi;
    u32 control,status;
    unsigned long base,db;
    if(elden_pci_state.owner!=ab||requested!=0x3004U||elden_pci_state.states>=16)return;
    pci=ath12k_pci_priv(ab);mhi=pci?pci->mhi_ctrl:NULL;
    if(!mhi||mhi->regs!=ab->mem||mhi->reg_len!=ab->mem_len||
       mhi->mhi_dev!=elden_umac_device)return;
    control=ioread32(ab->mem+0x38U);status=ioread32(ab->mem+0x48U);
    base=(unsigned long)ab->mem;db=(unsigned long)mhi->wake_db;
    ath12k_warn(ab,"ELDEN_PCI_STATE sample=%u wake=%x ctl=%x status=%x pm=%x state=%u ee=%u refs=%d devrefs=%u db-off=%llx installed=%u\n",
        ++elden_pci_state.states,observed,control,status,READ_ONCE(mhi->pm_state),
        (unsigned)READ_ONCE(mhi->dev_state),(unsigned)READ_ONCE(mhi->ee),
        atomic_read(&mhi->dev_wake),READ_ONCE(mhi->mhi_dev->dev_wake),
        (unsigned long long)(db>=base&&db-base<ab->mem_len?db-base:~0UL),
        elden_pci_state.installed);
    if(observed!=1U)elden_pci_state_dump(ab);
}

static void elden_pci_state_remove(struct ath12k_base *ab)
{
    void (*expected)(volatile void *,u32)=elden_pci_state_mmio;
    if(elden_pci_state.owner!=ab)return;
    elden_pci_state_dump(ab);
    if(elden_pci_state.installed&&__atomic_compare_exchange_n(&lx_mmio_trace,
            &expected,NULL,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)){
        elden_pci_state.installed=false;elden_pci_state.owner=NULL;
        ath12k_warn(ab,"ELDEN_PCI_STATE removed=1\n");
    }else ath12k_warn(ab,"ELDEN_PCI_STATE remove-refused changed-observer=1\n");
}
