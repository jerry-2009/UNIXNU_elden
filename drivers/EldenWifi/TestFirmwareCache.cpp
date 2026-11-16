/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "FirmwareCache.h"
#include "ModemFiles.h"
#include <CommonCrypto/CommonDigest.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <vector>
#include <atomic>
#include <thread>
using boolean_t=int;using IOLock=std::mutex;using SHA256_CTX=CC_SHA256_CTX;
static void SHA256_Init(SHA256_CTX *c){CC_SHA256_Init(c);}
static void SHA256_Update(SHA256_CTX *c,const void *p,size_t n){assert(n<=65536);CC_SHA256_Update(c,p,(CC_LONG)n);}
static void SHA256_Final(uint8_t *p,SHA256_CTX *c){CC_SHA256_Final(p,c);}
static unsigned checks,cases,allocations_count,fail_alloc,reads,fail_read,corruptions;
static bool live=true,in_irq=false,corrupt=false;
static std::atomic<bool> block_read{false},read_entered{false},release_read{false};
static int owner;static FILE *disk;
static std::vector<void *> allocations;static std::vector<IOLock *> locks;
#define CHECK(x) do{++checks;assert(x);}while(0)
static bool allocation_fails(){return ++allocations_count==fail_alloc;}
static void *IOMalloc(size_t n){if(allocation_fails())return nullptr;void *p=malloc(n);if(p)allocations.push_back(p);return p;}
static void IOFree(void *,size_t){assert(false&&"cache must retain buffers until reset");}
static IOLock *IOLockAlloc(){if(allocation_fails())return nullptr;auto p=new IOLock;locks.push_back(p);return p;}
static void IOLockLock(IOLock *p){p->lock();}static void IOLockUnlock(IOLock *p){p->unlock();}
static bool IOLockTryLock(IOLock *p){return p->try_lock();}
extern "C" boolean_t ml_at_interrupt_context(){return in_irq;}
extern "C" int elden_wlan_power_ready(const void *p,uint64_t e){return p==&owner&&e==7&&live?0:-19;}
extern "C" int native_ufs_part_find(const char *name,uint32_t *lun,uint64_t *first,uint64_t *blocks){
    assert(!strcmp(name,"modem_a"));*lun=4;*first=4870;*blocks=89600;return 1;
}
extern "C" int native_ufs_part_read(uint32_t lun,uint64_t first,uint32_t blocks,void *data){
    assert(lun==4&&first>=4870&&blocks&&blocks<=256&&first-4870+blocks<=89600);reads++;
    if(block_read){read_entered=true;while(!release_read)std::this_thread::yield();}
    if(fail_read&&reads==fail_read)return 0;
    if(fseeko(disk,(off_t)((first-4870)*4096),SEEK_SET)||fread(data,4096,blocks,disk)!=blocks)return 0;
    if(corrupt&&blocks>1){((uint8_t *)data)[0]^=1;corruptions++;}
    return 1;
}
#include "FirmwareCacheHost.inc"
static void reset(){
    for(auto p:locks)delete p;locks.clear();for(auto p:allocations)free(p);allocations.clear();
    cache=nullptr;run=stopping=0;setup_error=0;allocations_count=fail_alloc=reads=fail_read=corruptions=0;
    live=true;in_irq=corrupt=false;block_read=false;read_entered=false;release_read=false;++cases;
}
static EldenWifiFirmwareStatus status(){EldenWifiFirmwareStatus s={};CHECK(!elden_wifi_firmware_status(&s));return s;}
static void bind(){CHECK(elden_wifi_firmware_bind(&owner,7)==0);}
int main(int argc,char **argv){
    CHECK(argc==2);disk=fopen(argv[1],"rb");CHECK(disk);const uint8_t *data=nullptr;size_t bytes=0;
    reset();CHECK(status().run==0);CHECK(elden_wifi_firmware_bind(&owner,8)==-19);bind();
    CHECK(elden_wifi_firmware_bind(&owner,7)==-16);
    const char *names[]={"ath12k/PEACH/hw2.0/amss.bin","PEACH/hw2.0/m3.bin","aux_ucode.bin","tmel.bin","regdb.bin","board.bin"};
    const unsigned slots[]={0,1,2,3,5,6};
    for(unsigned i=0;i<6;i++){
        CHECK(elden_wifi_firmware_get(names[i],&data,&bytes)==0&&data&&bytes==elden_wifi_firmware_inputs[slots[i]].bytes);
        const uint8_t *saved=data;unsigned old_reads=reads;CHECK(elden_wifi_firmware_get(names[i],&data,&bytes)==0&&data==saved&&reads==old_reads);
    }
    CHECK(status().loaded==6&&status().bytes==7517874);
    unsigned old_reads=reads;
    for(const char *bad:{"../m3.bin","ath12k/WCN7850/hw2.0/m3.bin","firmware-2.bin","data20.msc"})
        CHECK(elden_wifi_firmware_get(bad,&data,&bytes)==-2&&!data&&!bytes&&reads==old_reads);
    elden_wifi_firmware_stop_begin();CHECK(elden_wifi_firmware_get("m3.bin",&data,&bytes)==-108&&!data&&!bytes);
    CHECK(status().loaded==6&&allocations.size()==7);
    for(unsigned n=1;n<=2;n++){
        reset();fail_alloc=n;CHECK(elden_wifi_firmware_bind(&owner,7)==-12);CHECK(status().run==3&&status().error==-12);
    }
    reset();bind();fail_alloc=3;CHECK(elden_wifi_firmware_get("m3.bin",&data,&bytes)==-12&&!data);CHECK(status().loaded==0);
    reset();bind();fail_read=1;CHECK(elden_wifi_firmware_get("amss.bin",&data,&bytes)!=0&&!data);
    old_reads=reads;CHECK(elden_wifi_firmware_get("amss.bin",&data,&bytes)!=0&&reads==old_reads);
    reset();bind();corrupt=true;CHECK(elden_wifi_firmware_get("amss.bin",&data,&bytes)==-74&&!data&&!bytes&&corruptions>0);
    CHECK(status().loaded==0&&status().error==-74&&allocations.size()==2);
    reset();bind();block_read=true;int result=0;
    std::thread loader([&]{result=elden_wifi_firmware_get("m3.bin",&data,&bytes);});
    while(!read_entered)std::this_thread::yield();EldenWifiFirmwareStatus busy={};CHECK(elden_wifi_firmware_status(&busy)==-11);
    elden_wifi_firmware_stop_begin();release_read=true;loader.join();CHECK(result==-108&&!data&&!bytes&&status().stopping==1);
    reset();bind();in_irq=true;CHECK(elden_wifi_firmware_get("m3.bin",&data,&bytes)==-22&&!reads);in_irq=false;
    unsigned completed=cases;reset();fclose(disk);
    printf("%u actual firmware-cache scenarios / %u checks passed using original modem FAT and real SHA256; kernel services modeled\n",completed,checks);
}
