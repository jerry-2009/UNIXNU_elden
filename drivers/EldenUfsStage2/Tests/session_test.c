/* SPDX-License-Identifier: GPL-3.0-only */
#include "EldenUfsSession.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static _Alignas(4096) uint8_t arena[8192];
static struct fixture {
    uint32_t reg[0x304/4];
    uint8_t disk[64][4096];
    uint64_t ticks;
    unsigned writes,submits,admissions,reject_at;
    bool ignore_restore;
} f;
static struct elden_ufs_session session;
static void le32(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(n>>(8*i));}
static void le64(uint8_t *p,uint64_t n){for(unsigned i=0;i<8;++i)p[i]=(uint8_t)(n>>(8*i));}
static uint64_t be64(const uint8_t *p){uint64_t n=0;for(unsigned i=0;i<8;++i)n=n*256+p[i];return n;}
static void putbe32(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;++i)p[3-i]=(uint8_t)(n>>(8*i));}
static uint32_t crc(const uint8_t *p,size_t n)
{
    uint32_t c=~0u;
    while(n--){c^=*p++;for(unsigned i=0;i<8;++i)c=(c>>1)^((c&1)?0xedb88320u:0);}
    return ~c;
}
static void reset_fixture(void)
{
    memset(&f,0,sizeof(f));memset(&session,0,sizeof(session));
    f.reg[0]=1u<<24;f.reg[0x34/4]=1;f.reg[0x30/4]=0x10f;
    f.reg[0x50/4]=0x90000000;f.reg[0x60/4]=1;f.reg[0x24/4]=0x55;
    uint8_t *h=f.disk[1],*e=f.disk[2];
    memcpy(h,"EFI PART",8);le32(h+8,0x10000);le32(h+12,92);
    le64(h+24,1);le64(h+32,63);le64(h+40,6);le64(h+48,58);
    h[56]=1;le64(h+72,2);le32(h+80,4);le32(h+84,128);
    e[0]=2;e[16]=3;le64(e+32,8);le64(e+40,23);
    const char *name="ARMADA_BACKUP";
    for(unsigned i=0;name[i];++i)e[56+2*i]=(uint8_t)name[i];
    le32(h+88,crc(e,512));le32(h+16,crc(h,92));
    for(unsigned b=8;b<=23;++b)for(unsigned i=0;i<4096;++i)f.disk[b][i]=(uint8_t)(b*37+i);
}
static int rd(void *ctx,uint32_t offset,uint32_t *out)
{struct fixture *x=ctx;assert(offset<sizeof(x->reg));*out=x->reg[offset/4];return 0;}
static int wr(void *ctx,uint32_t offset,uint32_t value)
{
    struct fixture *x=ctx;assert(offset<sizeof(x->reg));++x->writes;
    if(offset==0x20){x->reg[offset/4]&=~value;return 0;}
    if(offset==0x50&&value==0x90000000&&x->ignore_restore)return 0;
    x->reg[offset/4]=value;
    if(offset!=0x58)return 0;
    ++x->submits;assert(value==1);
    uint8_t *q=arena+1024,*r=arena+1536,*c=q+16;
    unsigned direction=(arena[3]>>1)&3;
    assert(direction!=1);memset(r,0,512);r[0]=q[0]+0x20;r[2]=q[2];
    if(q[0]==0x16){
        assert(q[5]==1&&q[12]==3&&q[13]==2);
        memcpy(r+12,q+12,4);putbe32(r+20,0x11);
    } else if(q[0]==1){
        assert(q[2]==4);
        if(c[0]==0x9e){
            assert(direction==2&&c[1]==0x10);memset(arena+4096,0,32);
            arena[4103]=63;putbe32(arena+4104,4096);
        } else if(c[0]==0x88){
            uint64_t lba=be64(c+2);assert(lba<64&&direction==2&&c[13]==1);
            memcpy(arena+4096,x->disk[lba],4096);
        } else assert(c[0]==0&&direction==0);
    } else assert(q[0]==0&&direction==0);
    arena[8]=0;x->reg[0x58/4]=0;return 0;
}
static void sync_buffer(void *ctx,void *p,size_t n){(void)ctx;(void)p;(void)n;}
static uint64_t ticks(void *ctx){return ((struct fixture *)ctx)->ticks;}
static void delay(void *ctx,uint32_t us){((struct fixture *)ctx)->ticks+=(us+999)/1000;}
static int admit(void *ctx,uint64_t physical,size_t bytes)
{
    struct fixture *x=ctx;++x->admissions;
    assert(physical==0xa0000000&&bytes==8192);
    return x->reject_at&&x->admissions>=x->reject_at;
}
static struct elden_ufs_backend backend(void)
{struct elden_ufs_backend b={{&f,rd,wr,sync_buffer,sync_buffer,ticks,delay,false},admit};return b;}
static int open_session(void)
{struct elden_ufs_backend b=backend();return elden_ufs_open(&session,&b,arena,sizeof(arena),0xa0000000);}

int main(void)
{
    reset_fixture();assert(open_session()==0);
    assert(session.lun.number==4&&!session.lun.block.write&&!session.lun.block.flush);
    assert(elden_ufs_partition_bytes(&session)==16*4096);
    uint8_t output[8197];assert(elden_ufs_read(&session,4093,sizeof(output),output)==0);
    assert(!memcmp(output,(uint8_t *)f.disk[8]+4093,sizeof(output)));
    unsigned before=f.submits;
    assert(elden_ufs_read(&session,16*4096-2,3,output)==KSHIM_STORAGE_RANGE&&f.submits==before);
    memset(arena,0,sizeof(arena));arena[3]=0x13;arena[1024]=1;arena[1026]=4;arena[1040]=0x8a;
    assert(session.host.ops.write32(session.host.ops.ctx,0x58,1)!=0&&f.submits==before);
    before=f.writes;assert(session.host.ops.write32(session.host.ops.ctx,0x34,0)!=0&&f.writes==before);
    assert(elden_ufs_close(&session)==0&&elden_ufs_can_handoff(&session));
    assert(f.reg[0x50/4]==0x90000000&&f.reg[0x60/4]==1&&f.reg[0x24/4]==0x55);
    assert(elden_ufs_open(&session,&session.backend,arena,sizeof(arena),0xa0000000)==0);
    assert(elden_ufs_close(&session)==0);

    reset_fixture();f.reject_at=1;assert(open_session()!=0&&f.writes==0);
    assert(elden_ufs_close(&session)==0&&elden_ufs_can_handoff(&session));
    reset_fixture();assert(open_session()==0);before=f.submits;f.reject_at=f.admissions+1;
    assert(elden_ufs_read(&session,0,1,output)!=0&&f.submits==before);
    assert(elden_ufs_close(&session)==0&&elden_ufs_can_handoff(&session));
    reset_fixture();f.disk[2][100]^=1;assert(open_session()==KSHIM_STORAGE_CRC);
    assert(elden_ufs_close(&session)==0&&elden_ufs_can_handoff(&session));
    reset_fixture();assert(open_session()==0);f.ignore_restore=true;
    assert(elden_ufs_close(&session)!=0&&!elden_ufs_can_handoff(&session));
    assert(session.state==ELDEN_UFS_QUARANTINED&&open_session()==KSHIM_UFS_BUSY);
    reset_fixture();struct elden_ufs_backend b=backend();
    assert(elden_ufs_open(&session,&b,NULL,8192,0xa0000000)==KSHIM_STORAGE_ARG&&f.admissions==0);
    puts("session: readonly wire guard, bounded partition reads, fresh DMA admission, GPT CRC and release readback PASS");
    return 0;
}
