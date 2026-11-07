/* SPDX-License-Identifier: GPL-3.0-only */
#include <Uefi.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include "EldenUfsHardware.h"

#define HC_BASE 0x01d84000ULL
#define SMMU_BASE 0x15000000ULL
#define GCC_PAGE 0x00177000ULL

static UINT32 mmio(UINT64 Address)
{
    UINT32 Value;
    __asm__ volatile("dsb sy" ::: "memory");
    Value=*(volatile UINT32 *)(UINTN)Address;
    __asm__ volatile("dsb sy" ::: "memory");
    return Value;
}
static BOOLEAN mapped(UINT64 Address,UINTN Bytes,BOOLEAN Write)
{
    UINT64 Saved,Par,Page;
    BOOLEAN Valid=TRUE;
    if((Address&4095)||(Bytes&4095)||!Bytes||Bytes>0x100000)return FALSE;
    __asm__ volatile("mrs %0, par_el1":"=r"(Saved));
    for(Page=0;Page<Bytes;Page+=4096){
        UINT64 Virtual=Address+Page;
        if(Write)__asm__ volatile("at s1e1w, %1\n\tisb\n\tmrs %0, par_el1":"=r"(Par):"r"(Virtual):"memory");
        else __asm__ volatile("at s1e1r, %1\n\tisb\n\tmrs %0, par_el1":"=r"(Par):"r"(Virtual):"memory");
        if((Par&1)||(Par&0x000ffffffffff000ULL)!=Virtual){Valid=FALSE;break;}
    }
    __asm__ volatile("msr par_el1, %0\n\tisb"::"r"(Saved):"memory");
    return Valid;
}

// This component is for the SM8750 inherited controller only. Inspect the
// actual boot FDT before any fixed-address MMIO, not the chosen menu label.
static BOOLEAN sun_platform(CONST UINT8 *Fdt)
{
    UINT32 At=SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+8)));
    UINT32 Strings=SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+12)));
    UINT32 End=At+SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+36)));
    if(SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+At)))!=1)return FALSE;
    At+=4;while(At<End&&Fdt[At])++At;At=(At+4)&~3U;
    while(At+4<=End){
        UINT32 Token=SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+At)));At+=4;
        if(Token==4)continue;
        if(Token!=3||At+8>End)break;
        UINT32 Length=SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+At)));
        UINT32 Name=SwapBytes32(ReadUnaligned32((CONST UINT32 *)(Fdt+At+4)));At+=8;
        if(Length>End-At)return FALSE;
        if(AsciiStrCmp((CONST CHAR8 *)Fdt+Strings+Name,"compatible")==0){
            UINT32 Offset=0;
            while(Offset<Length){
                CONST CHAR8 *Value=(CONST CHAR8 *)Fdt+At+Offset;
                UINT32 N=0;while(Offset+N<Length&&Value[N])++N;
                if(Offset+N==Length)return FALSE;
                if((N==8&&CompareMem(Value,"qcom,sun",8)==0)||(N==11&&CompareMem(Value,"qcom,sm8750",11)==0))return TRUE;
                Offset+=N+1;
            }
            return FALSE;
        }
        At=(At+Length+3)&~3U;
    }
    return FALSE;
}

// Exact SID 0x60 match, no translation tables and no SMMU writes. Narrowly
// admits the bypass or stage-1-disabled/stage-2-bypass state already observed.
static int admit_dma(void *Context,uint64_t Physical,size_t Bytes)
{
    ELDEN_UFS_HARDWARE *H=Context;
    UINT32 Cr0,Id0,Id1,Id2,Streams,Banks,Pages,Matches=0,Slot=0,Smr=0,Route,Bank;
    CONST UINT32 Width[]={32,36,40,42,44,48};
    if(Physical!=H->Arena||Bytes!=8192||!mapped(Physical,Bytes,TRUE))return -1;
    Cr0=mmio(SMMU_BASE);Id0=mmio(SMMU_BASE+0x20);Id1=mmio(SMMU_BASE+0x24);Id2=mmio(SMMU_BASE+0x28);
    Streams=Id0&255;Banks=Id1&255;Pages=1U<<(((Id1>>28)&7)+1);
    if((Cr0&9)||(Id0&0x48000000U)!=0x48000000U||!(Id2&0x1000)||(Id1&0x80000000U)||
       !Streams||!Banks||Banks>Pages||((Id1>>16)&255)>Banks||Pages*8192U>0x100000U)return -1;
    UINT32 Ias=Id2&15,Oas=(Id2>>4)&15;
    if(Ias>5||Oas>5||Physical>MAX_UINT64-Bytes||Physical+Bytes>(1ULL<<Width[Ias])||Physical+Bytes>(1ULL<<Width[Oas]))return -1;
    for(UINT32 I=0;I<Streams;++I){
        UINT32 V=mmio(SMMU_BASE+0x800+4*I),Mask=(V>>16)&0x7fff;
        if((V&0x80000000U)&&!((V^0x60)&0xffff&~Mask)){++Matches;Slot=I;Smr=V;}
    }
    if(Matches!=1||(Smr&0xffff)!=0x60||((Smr>>16)&0x7fff))return -1;
    Route=mmio(SMMU_BASE+0xc00+4*Slot);
    if(((Route>>16)&3)==1)return 0;
    if((Route>>16)&3)return -1;
    Bank=Route&255;
    if(Bank>=Banks||Bank<((Id1>>16)&255))return -1;
    if(((mmio(SMMU_BASE+0x1000+4*Bank)>>16)&3)!=1||!(mmio(SMMU_BASE+0x1800+4*Bank)&1)||
       (mmio(SMMU_BASE+(Pages+Bank)*4096)&1))return -1;
    return 0;
}
static int read32(void *Context,uint32_t Offset,uint32_t *Value)
{(VOID)Context;if(!Value||(Offset&3)||Offset>=0x3000)return -1;*Value=mmio(HC_BASE+Offset);return 0;}
static int write32(void *Context,uint32_t Offset,uint32_t Value)
{
    (VOID)Context;
    if((Offset&3)||Offset>=0x3000)return -1;
    __asm__ volatile("dsb sy" ::: "memory");
    *(volatile UINT32 *)(UINTN)(HC_BASE+Offset)=Value;
    __asm__ volatile("dsb sy" ::: "memory");
    return 0;
}
static void sync_device(void *Context,void *Buffer,size_t Bytes)
{
    ELDEN_UFS_HARDWARE *H=Context;UINTN At=(UINTN)Buffer;
    for(UINTN End=At+Bytes;At<End;At+=H->CacheLine)__asm__ volatile("dc civac, %0"::"r"(At):"memory");
    __asm__ volatile("dsb sy" ::: "memory");
}
static void sync_cpu(void *Context,void *Buffer,size_t Bytes)
{
    ELDEN_UFS_HARDWARE *H=Context;UINTN At=(UINTN)Buffer;
    __asm__ volatile("dsb sy" ::: "memory");
    for(UINTN End=At+Bytes;At<End;At+=H->CacheLine)__asm__ volatile("dc ivac, %0"::"r"(At):"memory");
    __asm__ volatile("dsb sy" ::: "memory");
}
static uint64_t now_ms(void *Context)
{
    ELDEN_UFS_HARDWARE *H=Context;UINT64 Ticks;
    __asm__ volatile("mrs %0, cntpct_el0":"=r"(Ticks));
    return (Ticks/H->CounterFrequency)*1000+(Ticks%H->CounterFrequency)*1000/H->CounterFrequency;
}
static void delay_us(void *Context,uint32_t Microseconds)
{(VOID)Context;gBS->Stall(Microseconds);}
static BOOLEAN clock_on(UINT32 V){return (V&3)&&(!(V&0x80000000U)||(V&2));}

EFI_STATUS EldenUfsHardwareOpen(EFI_HANDLE SourceVolume,ELDEN_UFS_HARDWARE *H)
{
    EFI_STATUS Status;VOID *Fdt;UINT64 El,Sctlr,Ctr;
    if(!H||H->Allocated||H->Session.state!=ELDEN_UFS_CLOSED)return EFI_INVALID_PARAMETER;
    Status=EldenPrepareFdt(SourceVolume,&H->Fdt);if(EFI_ERROR(Status))return Status;
    Status=EfiGetSystemConfigurationTable(&gFdtTableGuid,&Fdt);
    if(EFI_ERROR(Status)||!sun_platform(Fdt))return EFI_UNSUPPORTED;
    __asm__ volatile("mrs %0, CurrentEL\n\tmrs %1, sctlr_el1\n\tmrs %2, ctr_el0":"=r"(El),"=r"(Sctlr),"=r"(Ctr));
    if(El!=4||!(Sctlr&1))return EFI_UNSUPPORTED;
    H->CacheLine=4ULL<<((Ctr>>16)&15);
    __asm__ volatile("mrs %0, cntfrq_el0":"=r"(H->CounterFrequency));
    if(H->CacheLine>4096||!H->CounterFrequency)return EFI_UNSUPPORTED;
    if(!mapped(GCC_PAGE,4096,FALSE)||!mapped(HC_BASE,0x3000,TRUE)||!mapped(SMMU_BASE,0x100000,FALSE))return EFI_UNSUPPORTED;
    if(!(mmio(GCC_PAGE+4)&0x80000000U)||!clock_on(mmio(GCC_PAGE+0x18))||
       !clock_on(mmio(GCC_PAGE+0x28))||!clock_on(mmio(GCC_PAGE+0xf0)))return EFI_NOT_READY;
    H->Arena=MAX_UINT32;
    Status=gBS->AllocatePages(AllocateMaxAddress,EfiReservedMemoryType,2,&H->Arena);
    if(EFI_ERROR(Status))return Status;
    H->Allocated=TRUE;
    struct elden_ufs_backend Backend={{H,read32,write32,sync_device,sync_cpu,now_ms,delay_us,true},admit_dma};
    int Result=elden_ufs_open(&H->Session,&Backend,(VOID *)(UINTN)H->Arena,8192,H->Arena);
    if(Result){Print(L"ELDEN_UFS: stage %u failed %d\r\n",H->Session.stage,Result);return EFI_DEVICE_ERROR;}
    return EFI_SUCCESS;
}

EFI_STATUS EldenUfsHardwareClose(ELDEN_UFS_HARDWARE *H)
{
    EFI_STATUS Status;
    if(!H)return EFI_INVALID_PARAMETER;
    if(elden_ufs_close(&H->Session)||!elden_ufs_can_handoff(&H->Session))return EFI_DEVICE_ERROR;
    if(H->Allocated){
        Status=gBS->FreePages(H->Arena,2);if(EFI_ERROR(Status))return Status;
        H->Allocated=FALSE;H->Arena=0;
    }
    return EldenReleaseFdt(&H->Fdt);
}
