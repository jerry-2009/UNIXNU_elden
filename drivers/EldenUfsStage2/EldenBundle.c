/* SPDX-License-Identifier: GPL-3.0-only */
#include "EldenBundle.h"
#include <string.h>

static uint32_t le32(const uint8_t *p)
{return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static uint64_t le64(const uint8_t *p){return le32(p)|(uint64_t)le32(p+4)<<32;}

int elden_bundle_header(const uint8_t *h,uint64_t partition_bytes,
                        unsigned slot,struct elden_bundle *out)
{
    if(!h||!out||slot>1)return -1;
    const uint8_t magic[]="ELDSTG01";
    for(unsigned i=0;i<8;++i)if(h[i]!=magic[i])return -1;
    uint64_t span=(partition_bytes/2)&~(ELDEN_SLOT_DATA_OFFSET-1);
    if(span<64*ELDEN_SLOT_DATA_OFFSET||le32(h+8)!=1||le32(h+12)!=4096||
       !le64(h+16)||le64(h+64)!=span||le32(h+72)!=slot||le32(h+76))return -1;
    uint64_t bytes=le64(h+24);
    if(bytes<ELDEN_SLOT_DATA_OFFSET||bytes>ELDEN_BUNDLE_MAX_BYTES||
       bytes>span-ELDEN_SLOT_DATA_OFFSET||(bytes&511))return -1;
    for(unsigned i=80;i<4092;++i)if(h[i])return -1;
    if(kshim_crc32(h,4092)!=le32(h+4092))return -1;
    out->generation=le64(h+16);out->bytes=bytes;out->span=span;
    out->slot=slot;out->offset=slot*span+ELDEN_SLOT_DATA_OFFSET;
    memcpy(out->sha256,h+32,32);return 0;
}

/* FIPS 180-4 SHA-256, for update integrity (not authentication). */
static uint32_t ror(uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));}
static const uint32_t round_k[64]={
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
static void sha_block(uint32_t h[8],const uint8_t *p)
{
    uint32_t w[64],a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],x=h[7];
    for(unsigned i=0;i<16;++i)w[i]=(uint32_t)p[4*i]<<24|(uint32_t)p[4*i+1]<<16|(uint32_t)p[4*i+2]<<8|p[4*i+3];
    for(unsigned i=16;i<64;++i){
        uint32_t s0=ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3);
        uint32_t s1=ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10);
        w[i]=w[i-16]+s0+w[i-7]+s1;
    }
    for(unsigned i=0;i<64;++i){
        uint32_t t1=x+(ror(e,6)^ror(e,11)^ror(e,25))+((e&f)^(~e&g))+round_k[i]+w[i];
        uint32_t t2=(ror(a,2)^ror(a,13)^ror(a,22))+((a&b)^(a&c)^(b&c));
        x=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=x;
}
void elden_bundle_sha256(const void *buffer,size_t bytes,uint8_t digest[32])
{
    uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    const uint8_t *p=buffer;uint64_t bits=(uint64_t)bytes*8;uint8_t tail[128];
    memset(tail,0,sizeof(tail));
    while(bytes>=64){sha_block(h,p);p+=64;bytes-=64;}
    if(bytes)memcpy(tail,p,bytes);
    tail[bytes]=0x80;unsigned total=bytes<56?64:128;
    for(unsigned i=0;i<8;++i)tail[total-1-i]=(uint8_t)(bits>>(8*i));
    sha_block(h,tail);if(total==128)sha_block(h,tail+64);
    for(unsigned i=0;i<32;++i)digest[i]=(uint8_t)(h[i/4]>>(24-8*(i%4)));
}
int elden_bundle_verify(const struct elden_bundle *bundle,const void *buffer,size_t bytes)
{
    uint8_t digest[32];unsigned difference=0;
    if(!bundle||!buffer||bytes!=bundle->bytes||bytes>ELDEN_BUNDLE_MAX_BYTES)return -1;
    elden_bundle_sha256(buffer,bytes,digest);
    for(unsigned i=0;i<32;++i)difference|=digest[i]^bundle->sha256[i];
    return difference?-1:0;
}

int elden_bundle_load(const struct elden_bundle_reader *r,uint64_t partition_bytes,
                      int previous,struct elden_bundle *selected,void **buffer)
{
    uint8_t header[4096];struct elden_bundle bundle[2];int valid[2];
    if(!r||!r->read||!r->allocate||!r->free||!selected||!buffer||(previous!=0&&previous!=1))
        return ELDEN_BUNDLE_ARGUMENT;
    *buffer=NULL;memset(selected,0,sizeof(*selected));
    uint64_t span=(partition_bytes/2)&~(ELDEN_SLOT_DATA_OFFSET-1);
    if(span<64*ELDEN_SLOT_DATA_OFFSET)return ELDEN_BUNDLE_NOT_FOUND;
    for(unsigned i=0;i<2;++i){
        if(r->read(r->context,i*span,sizeof(header),header))return ELDEN_BUNDLE_IO;
        valid[i]=elden_bundle_header(header,partition_bytes,i,&bundle[i])==0;
    }
    if(!valid[0]&&!valid[1])return ELDEN_BUNDLE_NOT_FOUND;
    unsigned newest=valid[0]?0:1;
    if(valid[0]&&valid[1]){
        if(bundle[0].generation==bundle[1].generation)return ELDEN_BUNDLE_AMBIGUOUS;
        newest=bundle[1].generation>bundle[0].generation?1:0;
    }
    if(previous&&!valid[1-newest])return ELDEN_BUNDLE_NOT_FOUND;
    unsigned index=previous?1-newest:newest;
    for(unsigned attempt=0;attempt<(previous?1U:2U);++attempt,index=1-index){
        if(!valid[index])continue;
        void *data=r->allocate(r->context,(size_t)bundle[index].bytes);
        if(!data)return ELDEN_BUNDLE_MEMORY;
        if(r->read(r->context,bundle[index].offset,(size_t)bundle[index].bytes,data)){
            r->free(r->context,data);return ELDEN_BUNDLE_IO;
        }
        if(!elden_bundle_verify(&bundle[index],data,(size_t)bundle[index].bytes)){
            memcpy(selected,&bundle[index],sizeof(*selected));*buffer=data;return ELDEN_BUNDLE_OK;
        }
        r->free(r->context,data);
    }
    return ELDEN_BUNDLE_DIGEST;
}
