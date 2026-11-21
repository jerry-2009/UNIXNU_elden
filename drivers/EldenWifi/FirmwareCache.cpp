/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "FirmwareCache.h"
#include "ModemFiles.h"
#include "EldenWifiResources.h"
#include "EldenWifiFirmwareInputs.h"
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <libkern/crypto/sha2.h>
#include <string.h>
extern "C" {
int native_ufs_part_find(const char *,uint32_t *,uint64_t *,uint64_t *);
int native_ufs_part_read(uint32_t,uint64_t,uint32_t,void *);
int elden_wlan_power_ready(const void *,uint64_t);
boolean_t ml_at_interrupt_context(void);
}
namespace {
struct Entry {uint8_t *data=nullptr;size_t bytes=0;bool ready=false;};
struct Cache {
    static void *operator new(size_t n) noexcept{return IOMalloc(n);}
    static void operator delete(void *p) noexcept{if(p)IOFree(p,sizeof(Cache));}
    const void *provider=nullptr;uint64_t epoch=0;
    IOLock *lock=nullptr;EldenWifiFiles files={};Entry entries[sizeof(elden_wifi_firmware_inputs)/sizeof(elden_wifi_firmware_inputs[0])];
    unsigned loaded=0,slot=0;uint64_t bytes=0;int error=0;
};
static Cache *cache;
static unsigned run,stopping;
static int setup_error;
static bool qualified(const Cache *c){return c&&!__atomic_load_n(&stopping,__ATOMIC_ACQUIRE)&&elden_wlan_power_ready(c->provider,c->epoch)==0;}
static int find(void *p,const char *name,uint32_t *lun,uint64_t *first,uint64_t *blocks){return qualified((Cache *)p)?native_ufs_part_find(name,lun,first,blocks):0;}
static int read(void *p,uint32_t lun,uint64_t first,uint32_t blocks,void *data){return qualified((Cache *)p)?native_ufs_part_read(lun,first,blocks,data):0;}
static int slot_for(const char *name){
    if(!name)return -1;size_t size=0;while(size<128&&name[size])size++;if(!size||size==128)return -1;
    const char *base=name;
    static const char full[]="ath12k/PEACH/hw2.0/",short_name[]="PEACH/hw2.0/";
    if(!strncmp(base,full,sizeof(full)-1))base+=sizeof(full)-1;
    else if(!strncmp(base,short_name,sizeof(short_name)-1))base+=sizeof(short_name)-1;
    static const struct {const char *name;unsigned slot;} names[]={
        {"amss.bin",0},{"m3.bin",1},{"aux_ucode.bin",2},{"tmel.bin",3},{"regdb.bin",5},{"board.bin",6},
        {"qdss_trace_config.bin",7}};
    for(const auto &entry:names)if(!strcmp(base,entry.name))return (int)entry.slot;
    return -1;
}
static int load(Cache *c,unsigned slot){
    const auto &expected=elden_wifi_firmware_inputs[slot];Entry &entry=c->entries[slot];
    if(entry.ready)return 0;
    EldenWifiFile file={};int rc=elden_wifi_file_open(&c->files,expected.path,&file);if(rc)return qualified(c)?rc:-108;
    if(file.file.size!=expected.bytes||!expected.bytes||expected.bytes>ELDEN_WIFI_FILE_MAX)return -74;
    entry.bytes=expected.bytes;entry.data=(uint8_t *)IOMalloc(entry.bytes);if(!entry.data)return -12;
    SHA256_CTX hash;SHA256_Init(&hash);
    for(size_t offset=0;offset<entry.bytes;){
        if(!qualified(c))return -108;
        size_t length=entry.bytes-offset;if(length>65536)length=65536;
        rc=elden_wifi_file_read(&file,offset,entry.data+offset,length);if(rc)return qualified(c)?rc:-108;
        SHA256_Update(&hash,entry.data+offset,length);offset+=length;
    }
    uint8_t digest[32];SHA256_Final(digest,&hash);
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++)if(expected.sha256[2*i]!=hex[digest[i]>>4]||expected.sha256[2*i+1]!=hex[digest[i]&15])return -74;
    if(!qualified(c))return -108;
    entry.ready=true;c->loaded++;c->bytes+=entry.bytes;return 0;
}
}
extern "C" int elden_wifi_firmware_bind(const void *provider,uint64_t epoch){
    if(!provider||!epoch||ml_at_interrupt_context())return -22;
    if(__atomic_load_n(&stopping,__ATOMIC_ACQUIRE)||elden_wlan_power_ready(provider,epoch))return -19;
    unsigned expected=0;if(!__atomic_compare_exchange_n(&run,&expected,1u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return -16;
    Cache *c=new Cache;int rc=-12;
    if(c){
        c->provider=provider;c->epoch=epoch;c->lock=IOLockAlloc();__atomic_store_n(&cache,c,__ATOMIC_RELEASE);
        if(c->lock){
            EldenWifiFileIo io={c,find,read,ELDEN_WIFI_MODEM_FIRST,ELDEN_WIFI_MODEM_BLOCKS};elden_wifi_files_init(&c->files,&io);
            rc=qualified(c)?0:-108;
        }
    }
    setup_error=rc;__atomic_store_n(&run,rc?3u:2u,__ATOMIC_RELEASE);return rc;
}
extern "C" int elden_wifi_firmware_get(const char *name,const uint8_t **data,size_t *bytes){
    if(data)*data=nullptr;if(bytes)*bytes=0;
    if(!data||!bytes||ml_at_interrupt_context())return -22;
    int slot=slot_for(name);if(slot<0)return -2;
    unsigned state=__atomic_load_n(&run,__ATOMIC_ACQUIRE);if(state!=2)return state==3?setup_error:-19;
    Cache *c=__atomic_load_n(&cache,__ATOMIC_ACQUIRE);IOLockLock(c->lock);
    int rc=c->error;
    if(!rc&&!qualified(c))rc=-108;
    if(!rc){c->slot=(unsigned)slot;rc=load(c,(unsigned)slot);}
    if(!rc&&!qualified(c))rc=-108;
    if(!rc){*data=c->entries[slot].data;*bytes=c->entries[slot].bytes;}
    else if(!c->error)c->error=rc;
    /* Retain even a failed read buffer: a storage failure must not trigger
     * a speculative free while lower-level DMA state may be uncertain. */
    IOLockUnlock(c->lock);return rc;
}
extern "C" void elden_wifi_firmware_stop_begin(void){__atomic_store_n(&stopping,1u,__ATOMIC_RELEASE);}
extern "C" int elden_wifi_firmware_status(EldenWifiFirmwareStatus *out){
    if(!out||ml_at_interrupt_context())return -22;
    unsigned state=__atomic_load_n(&run,__ATOMIC_ACQUIRE);if(state==1)return -11;
    EldenWifiFirmwareStatus s={};s.version=1;s.run=state;s.stopping=__atomic_load_n(&stopping,__ATOMIC_ACQUIRE);
    if(state>=2){
        Cache *c=__atomic_load_n(&cache,__ATOMIC_ACQUIRE);
        if(c&&c->lock){
            if(!IOLockTryLock(c->lock))return -11;
            s.loaded=c->loaded;s.slot=c->slot;s.reads=c->files.reads;s.bytes=c->bytes;s.epoch=c->epoch;s.error=c->error?c->error:setup_error;
            IOLockUnlock(c->lock);
        }else s.error=setup_error;
    }
    *out=s;return 0;
}
