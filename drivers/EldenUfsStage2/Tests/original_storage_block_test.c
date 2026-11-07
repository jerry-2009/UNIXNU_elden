/* SPDX-License-Identifier: GPL-3.0-only */
#include "storage_block.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char disk[4096u * 1024u], scratch[8192];
static unsigned reads, writes;
static int read_error;
static struct kshim_blockdev dev;
static void le32(unsigned char *p, uint32_t n) { for (unsigned i=0;i<4;i++) p[i]=(unsigned char)(n>>(8*i)); }
static void le64(unsigned char *p, uint64_t n) { for (unsigned i=0;i<8;i++) p[i]=(unsigned char)(n>>(8*i)); }
/* Independent MSB-first polynomial division with explicit reflected input. */
static uint32_t fixture_crc(const unsigned char *p, size_t n) {
    uint32_t crc=~0u;
    while(n--) { unsigned char b=*p++; for(unsigned i=0;i<8;i++) {
        unsigned bit=((crc>>31) ^ (b>>i)) & 1u;
        crc<<=1; if(bit) crc^=0x04c11db7u;
    }}
    uint32_t out=0; for(unsigned i=0;i<32;i++) out|=((crc>>i)&1u)<<(31-i);
    return ~out;
}
static int rd(void *ctx,uint64_t lba,uint32_t n,void *p) {
    (void)ctx; reads++; if(read_error) return -1;
    assert(lba+n<=dev.block_count); memcpy(p,disk+lba*dev.block_size,(size_t)n*dev.block_size); return 0;
}
static int wr(void *ctx,uint64_t lba,uint32_t n,const void *p) {
    (void)ctx; writes++; assert(lba+n<=dev.block_count);
    memcpy(disk+lba*dev.block_size,p,(size_t)n*dev.block_size); return 0;
}
static int fl(void *ctx) { (void)ctx; return 0; }
static unsigned char *entry(unsigned n) { return disk+2*dev.block_size+n*128; }
static void entry_name(unsigned char *e,const char *s) {
    memset(e+56,0,72); for(unsigned i=0;s[i];i++) e[56+2*i]=(unsigned char)s[i];
}
static void reseal(void) {
    unsigned char *h=disk+dev.block_size;
    le32(h+88,fixture_crc(entry(0),512)); le32(h+16,0); le32(h+16,fixture_crc(h,92));
}
static void fixture(unsigned block_size) {
    static const unsigned char uuid_gpt[16]={0x51,0x4a,0xe3,0xb0,0x12,0x64,0xec,0x45,0xb0,0x45,0xbe,0xf3,0x66,0x4d,0x14,0xd3};
    memset(disk,0,sizeof(disk)); dev=(struct kshim_blockdev){0,block_size,1024,rd,wr,fl};
    unsigned char *h=disk+block_size;
    memcpy(h,"EFI PART",8); le32(h+8,0x00010000); le32(h+12,92);
    le64(h+24,1); le64(h+32,1023); le64(h+40,34); le64(h+48,990); h[56]=1;
    le64(h+72,2); le32(h+80,4); le32(h+84,128);
    entry(0)[0]=1; entry(0)[16]=1; le64(entry(0)+32,100); le64(entry(0)+40,199); entry_name(entry(0),"unrelated");
    entry(1)[0]=1; memcpy(entry(1)+16,uuid_gpt,16); le64(entry(1)+32,300); le64(entry(1)+40,799); entry_name(entry(1),"ARMADA_BACKUP");
    reseal(); reads=writes=0; read_error=0;
}
static int find(struct kshim_partition *p) { return kshim_gpt_find_backup(&dev,p,scratch,sizeof(scratch)); }
static void test_boundaries(void) {
    /* Missing bounds checks would permit callbacks for past-end/wrapped IO. */
    fixture(512); unsigned before=reads;
    assert(kshim_block_read(&dev,1024,1,scratch)==KSHIM_STORAGE_RANGE);
    assert(kshim_block_read(&dev,UINT64_MAX,2,scratch)==KSHIM_STORAGE_RANGE);
    assert(kshim_block_read(&dev,0,0,scratch)==KSHIM_STORAGE_ARG);
    assert(reads==before);
    assert(kshim_block_read(&dev,1023,1,scratch)==0);
    assert(kshim_block_write(&dev,1024,1,scratch)==KSHIM_STORAGE_RANGE && writes==0);
    dev.block_size=1024; assert(kshim_block_read(&dev,0,1,scratch)==KSHIM_STORAGE_ARG);
    dev.block_size=512; dev.write=0; assert(kshim_block_write(&dev,0,1,scratch)==KSHIM_STORAGE_READ_ONLY);
    dev.flush=0; assert(kshim_block_flush(&dev)==KSHIM_STORAGE_READ_ONLY);
    read_error=1; assert(kshim_block_read(&dev,0,1,scratch)==KSHIM_STORAGE_IO);
}
static void test_gpt(unsigned bs) {
    /* Wrong GUID byte order, omitted checks or accepting first name wins fail here. */
    static const unsigned char want_uuid[16]={0xb0,0xe3,0x4a,0x51,0x64,0x12,0x45,0xec,0xb0,0x45,0xbe,0xf3,0x66,0x4d,0x14,0xd3};
    struct kshim_partition p;
    fixture(bs); assert(find(&p)==0); assert(p.first_lba==300 && p.last_lba==799);
    assert(memcmp(p.uuid,want_uuid,16)==0 && writes==0);
    fixture(bs); disk[bs+16]^=1; assert(find(&p)==KSHIM_STORAGE_CRC);
    fixture(bs); entry(3)[127]^=1; assert(find(&p)==KSHIM_STORAGE_CRC);
    fixture(bs); le64(entry(0)+40,300); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); le64(entry(1)+32,800); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); le64(entry(1)+40,991); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); le64(entry(0)+32,33); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); entry(2)[0]=1; entry(2)[16]=2; le64(entry(2)+32,150); le64(entry(2)+40,250); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); entry_name(entry(0),"ARMADA_BACKUP"); reseal(); assert(find(&p)==KSHIM_STORAGE_CONFLICT);
    fixture(bs); entry_name(entry(1),"ARMADA_BACKUP-old"); reseal(); assert(find(&p)==KSHIM_STORAGE_NOT_FOUND);
    fixture(bs); memset(entry(1)+16,0,16); reseal(); assert(find(&p)==KSHIM_STORAGE_FORMAT);
    fixture(bs); le64(disk+bs+72,1023); reseal(); assert(find(&p)==KSHIM_STORAGE_RANGE);
    fixture(bs); le64(disk+bs+32,1022); reseal(); assert(find(&p)==KSHIM_STORAGE_FORMAT);
    fixture(bs); le32(disk+bs+80,257); reseal(); assert(find(&p)==KSHIM_STORAGE_FORMAT);
    /* Extended entries and later-block corruption exercise the complete CRC,
     * including bytes beyond the selected partition and the first table block. */
    fixture(bs); memmove(entry(0)+4096,entry(1),128); le32(disk+bs+84,4096);
    le32(disk+bs+88,fixture_crc(entry(0),16384)); le32(disk+bs+16,0); le32(disk+bs+16,fixture_crc(disk+bs,92));
    assert(find(&p)==0 && p.first_lba==300 && p.last_lba==799);
    entry(0)[16383]^=1; assert(find(&p)==KSHIM_STORAGE_CRC);
    fixture(bs); le32(disk+bs+12,128); disk[bs+100]=17; le32(disk+bs+16,0); le32(disk+bs+16,fixture_crc(disk+bs,128));
    assert(find(&p)==0); disk[bs+100]^=1; assert(find(&p)==KSHIM_STORAGE_CRC);
    fixture(bs); read_error=1; assert(find(&p)==KSHIM_STORAGE_IO);
    fixture(bs); assert(kshim_gpt_find_backup(&dev,&p,scratch,8191)==KSHIM_STORAGE_ARG);
    assert(writes==0);
}
int main(void) {
    assert(fixture_crc((const unsigned char *)"123456789",9)==0xcbf43926u);
    test_boundaries(); test_gpt(512); test_gpt(4096);
    assert(kshim_crc32("123456789",9)==0xcbf43926u);
    assert(kshim_crc32("",0)==0);
    puts("PASS storage_block: bounds, 512/4096 GPT CRC, GUID, uniqueness, overlap, IO");
    return 0;
}
