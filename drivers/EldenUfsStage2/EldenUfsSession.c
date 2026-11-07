/* SPDX-License-Identifier: GPL-3.0-only */
#include "EldenUfsSession.h"
#include <string.h>

static int read32(void *context,uint32_t offset,uint32_t *value)
{
    struct elden_ufs_session *s=context;
    return s->backend.io.read32(s->backend.io.ctx,offset,value);
}

static bool read_command(const struct elden_ufs_session *s)
{
    const uint8_t *t=s->host.arena,*q=t+1024,*c=q+16;
    unsigned direction=(t[3]>>1)&3;
    if(direction==1)return false;
    if(q[0]==0)return direction==0&&q[2]==0;
    if(q[0]==0x16)return direction==0&&q[5]==1&&(q[12]==1||q[12]==3);
    if(q[0]!=1)return false;
    if(c[0]==0x1b){
        if(q[2]!=0xd0||direction!=0||c[1]||c[2]||c[3]||
           (c[4]!=0x10&&c[4]!=0x20&&c[4]!=0x30))return false;
        for(unsigned i=5;i<16;++i)if(c[i])return false;
        return true;
    }
    if(q[2]!=4)return false;
    if(c[0]==0)return direction==0;
    if(c[0]==0x9e)return direction==2&&c[1]==0x10;
    return direction==2&&(c[0]==0x88||c[0]==0x12);
}

static int write32(void *context,uint32_t offset,uint32_t value)
{
    struct elden_ufs_session *s=context;
    switch(offset){
    case 0x18:case 0x20:case 0x24:case 0x50:case 0x54:case 0x60:break;
    case 0x58:
        if(value!=1||!read_command(s)||s->backend.admit_dma(s->backend.io.ctx,
                  s->host.dma_address,KSHIM_UFS_DMA_BYTES)){
            ++s->blocked_commands;return KSHIM_STORAGE_READ_ONLY;
        }
        break;
    case 0x90:if(value!=1&&value!=0x17&&value!=0x18)return KSHIM_STORAGE_ARG;break;
    case 0x94:if(value!=0&&value!=0x00410000)return KSHIM_STORAGE_ARG;break;
    case 0x98:case 0x9c:if(value!=0)return KSHIM_STORAGE_ARG;break;
    default:return KSHIM_STORAGE_READ_ONLY;
    }
    return s->backend.io.write32(s->backend.io.ctx,offset,value);
}
static void sync_device(void *context,void *buffer,size_t bytes)
{struct elden_ufs_session *s=context;s->backend.io.sync_device(s->backend.io.ctx,buffer,bytes);}
static void sync_cpu(void *context,void *buffer,size_t bytes)
{struct elden_ufs_session *s=context;s->backend.io.sync_cpu(s->backend.io.ctx,buffer,bytes);}
static uint64_t now_ms(void *context)
{struct elden_ufs_session *s=context;return s->backend.io.now_ms(s->backend.io.ctx);}
static void delay_us(void *context,uint32_t value)
{struct elden_ufs_session *s=context;s->backend.io.delay_us(s->backend.io.ctx,value);}
static int failed(struct elden_ufs_session *s,int result)
{s->state=ELDEN_UFS_FAILED;s->result=result;return result;}

int elden_ufs_open(struct elden_ufs_session *s,const struct elden_ufs_backend *backend,
                   void *arena,size_t bytes,uint64_t physical)
{
    if(!s||!backend||!backend->admit_dma||!backend->io.read32||!backend->io.write32||
       !backend->io.sync_device||!backend->io.sync_cpu||!backend->io.now_ms||!backend->io.delay_us)
        return KSHIM_STORAGE_ARG;
    if(!arena||bytes<KSHIM_UFS_DMA_BYTES||((uintptr_t)arena&1023)||!physical||
       (physical&1023)||physical>UINT64_MAX-(KSHIM_UFS_DMA_BYTES-1))return KSHIM_STORAGE_ARG;
    if(s->state!=ELDEN_UFS_CLOSED)return KSHIM_UFS_BUSY;
    struct elden_ufs_backend saved=*backend;
    memset(s,0,sizeof(*s));s->backend=saved;s->state=ELDEN_UFS_OPENING;s->stage=1;
    if(saved.admit_dma(saved.io.ctx,physical,KSHIM_UFS_DMA_BYTES))return failed(s,KSHIM_STORAGE_ARG);
    struct kshim_ufs_ops ops={s,read32,write32,sync_device,sync_cpu,now_ms,delay_us,saved.io.manage_link};
    int rc;s->stage=2;
    if((rc=kshim_ufs_claim(&s->host,&ops,arena,bytes,physical)))return failed(s,rc);
    s->stage=3;if((rc=kshim_ufs_nop(&s->host)))return failed(s,rc);
    s->stage=4;if((rc=kshim_ufs_prepare_device(&s->host)))return failed(s,rc);
    s->stage=5;if((rc=kshim_ufs_open_lun(&s->host,4,false,&s->lun)))return failed(s,rc);
    if(s->lun.block.block_size!=4096||s->lun.block.block_count>UINT64_MAX/4096)
        return failed(s,KSHIM_UFS_UNSUPPORTED);
    s->stage=6;
    if((rc=kshim_gpt_find_backup(&s->lun.block,&s->partition,s->scratch,sizeof(s->scratch))))return failed(s,rc);
    s->state=ELDEN_UFS_READY;s->result=0;return 0;
}

uint64_t elden_ufs_partition_bytes(const struct elden_ufs_session *s)
{
    if(!s||s->state!=ELDEN_UFS_READY)return 0;
    return (s->partition.last_lba-s->partition.first_lba+1)*4096;
}

int elden_ufs_read(struct elden_ufs_session *s,uint64_t offset,size_t bytes,void *output)
{
    if(!s||s->state!=ELDEN_UFS_READY||s->busy)return KSHIM_UFS_BUSY;
    uint64_t length=elden_ufs_partition_bytes(s);
    if(!output||!bytes||offset>=length||bytes>length-offset)return KSHIM_STORAGE_RANGE;
    s->busy=true;s->stage=7;
    uint8_t *destination=output;
    while(bytes){
        size_t in_block=(size_t)(offset%4096),take=4096-in_block;
        if(take>bytes)take=bytes;
        int rc=s->lun.block.read(s->lun.block.ctx,s->partition.first_lba+offset/4096,1,s->scratch);
        if(rc){s->busy=false;return failed(s,rc);}
        memcpy(destination,s->scratch+in_block,take);
        destination+=take;offset+=take;bytes-=take;
    }
    s->busy=false;return 0;
}

int elden_ufs_close(struct elden_ufs_session *s)
{
    if(!s)return KSHIM_STORAGE_ARG;
    if(s->state==ELDEN_UFS_CLOSED)return 0;
    if(s->state==ELDEN_UFS_QUARANTINED)return KSHIM_UFS_QUARANTINED;
    if(s->busy)return KSHIM_UFS_BUSY;
    bool owned=s->host.owned!=0;s->stage=8;
    uint32_t expected[]={s->host.saved_base[0],s->host.saved_base[1],s->host.saved_run,s->host.saved_ie,s->host.saved_ahit};
    const uint32_t offsets[]={0x50,0x54,0x60,0x24,0x18};
    int rc=kshim_ufs_release(&s->host);
    if(rc)goto quarantine;
    if(owned){
        s->stage=9;
        for(unsigned i=0;i<5;++i){
            uint32_t actual;
            if(read32(s,offsets[i],&actual)||actual!=expected[i]){rc=KSHIM_STORAGE_IO;goto quarantine;}
        }
    }
    s->state=ELDEN_UFS_CLOSED;s->result=0;return 0;
quarantine:
    s->state=ELDEN_UFS_QUARANTINED;s->result=rc;return rc;
}

bool elden_ufs_can_handoff(const struct elden_ufs_session *s)
{return s&&s->state==ELDEN_UFS_CLOSED&&!s->host.owned;}
