// SPDX-License-Identifier: BSD-2-Clause-Patent
#if defined(ELDEN_PINNED_ROOT) && ELDEN_PINNED_ROOT
#if defined(NATIVE_VERIFIED_BLOCK) && NATIVE_VERIFIED_BLOCK
#error Select either signed-manifest verification or the AVB-kernel-pinned profile.
#endif
#if !NATIVE_UFS_READ_ONLY
#error The pinned profile requires the read-only UFS transport.
#endif
#include "EldenPinnedRoot.h"
struct EldenPinnedState {
  const NativeUfsBlock *owner;
  vm_offset_t storage;
  vm_size_t allocated;
  uint64_t blocks;
  bool sealed;
};
static EldenPinnedState gEldenPinned[2] = {};
static volatile unsigned gEldenPinBusy;
volatile uint64_t native_ufs_pinned_verified_blocks;
static void eldenReleasePinned(const NativeUfsBlock *owner) {
  for(unsigned i=0;i<2;i++) {
    EldenPinnedState &s=gEldenPinned[i];
    if(s.owner!=owner)continue;
    vm_offset_t p=s.storage;vm_size_t n=s.allocated;
    bzero(&s,sizeof(s));
    if(p)kmem_free(kernel_map,p,n);
  }
}
static const EldenPinnedState *eldenFindPinned(const NativeUfsBlock *owner) {
  for(unsigned i=0;i<2;i++)if(gEldenPinned[i].owner==owner&&__atomic_load_n(&gEldenPinned[i].sealed,__ATOMIC_ACQUIRE))return &gEldenPinned[i];
  return nullptr;
}
static bool eldenPinRootWindow(const NativeUfsBlock *owner,const char *name,
                               uint64_t absolute,uint64_t bytes,char uuid[37]) {
  const int index=eldenRootPinIndex(name,bytes);
  if(index<0||gRootLun!=0||strcmp(UFS_ROOT_PARTITION,"ipados")||!gStoreGeometry.valid||
     (absolute&4095)||absolute<gStoreGeometry.first*4096ULL||
     absolute>(gStoreGeometry.last+1)*4096ULL||bytes>(gStoreGeometry.last+1)*4096ULL-absolute)return false;
  if(!__sync_bool_compare_and_swap(&gEldenPinBusy,0,1))return false;
  EldenPinnedState &state=gEldenPinned[index];
  if(state.owner){__sync_lock_release(&gEldenPinBusy);return false;}
  state.owner=owner;
  struct IO {
    using Hash=SHA256_CTX;
    EldenPinnedState &state;
    const NativeUfsBlock *owner;
    const char *name;
    uint64_t absolute;
    uint64_t nextReport;
    bool allocate(uint64_t tableBytes) {
      if(tableBytes>SIZE_MAX-4095)return false;
      state.allocated=round_page((vm_size_t)tableBytes);state.blocks=tableBytes/32;
      if(kmem_alloc(kernel_map,&state.storage,state.allocated,
          static_cast<kma_flags_t>(KMA_KOBJECT|KMA_DATA),VM_KERN_MEMORY_SECURITY)!=KERN_SUCCESS) {
        state.storage=0;return false;
      }
      return true;
    }
    uint8_t *leaf(uint64_t index) {return reinterpret_cast<uint8_t*>(state.storage)+index*32;}
    static void init(Hash &h){SHA256_Init(&h);}
    static void update(Hash &h,const void *p,size_t n){SHA256_Update(&h,p,n);}
    static void final(Hash &h,uint8_t d[32]){SHA256_Final(d,&h);}
    static void hash(const void *p,size_t n,uint8_t d[32]){Hash h;init(h);update(h,p,n);final(h,d);}
    bool read(uint64_t offset,size_t n,void *p) {
      return hostRead4k(gRootLun,(absolute+offset)/4096,(uint32_t)(n/4096),p)==kIOReturnSuccess;
    }
    void progress(uint64_t at,uint64_t total) {
      if(at>=nextReport||at==total){IOLog("EldenRoot: verify %s %llu/%llu MiB\n",name,at>>20,total>>20);nextReport=at+(256ULL<<20);}
    }
    void discard(){eldenReleasePinned(owner);}
    bool protect() {
      if(vm_map_protect(kernel_map,state.storage,state.storage+state.allocated,VM_PROT_READ,TRUE)!=KERN_SUCCESS)return false;
      __atomic_store_n(&state.sealed,true,__ATOMIC_RELEASE);return true;
    }
  } io={state,owner,name,absolute,256ULL<<20};
  uint8_t *scratch=static_cast<uint8_t*>(IOMalloc(kDataMax));
  gRootDiagnostic.stage="AVB-kernel-pinned image and block hashes";
  EldenPinError result=scratch?eldenVerifyPinnedImage(kEldenRootPins[index],io,scratch,kDataMax):EldenPinAllocation;
  if(scratch)IOFree(scratch,kDataMax);
  gRootDiagnostic.verify=(uint32_t)result;
  if(result!=EldenPinOk)eldenReleasePinned(owner);
  else {
    strlcpy(uuid,kEldenRootPins[index].volumeUuid,37);
    IOLog("EldenRoot: %s complete SHA256 accepted; %llu protected block hashes; UUID %s\n",name,state.blocks,uuid);
  }
  __sync_lock_release(&gEldenPinBusy);
  return result==EldenPinOk;
}
static bool eldenPinnedRead(const EldenPinnedState *pin,uint64_t index,const void *p,size_t bytes) {
  if(!pin||!__atomic_load_n(&pin->sealed,__ATOMIC_ACQUIRE))return false;
  const bool ok=eldenVerifyPinnedBlock(reinterpret_cast<const uint8_t*>(pin->storage),pin->blocks,index,p,bytes,
    [](const void *p,size_t n,uint8_t d[32]){SHA256_CTX h;SHA256_Init(&h);SHA256_Update(&h,p,n);SHA256_Final(d,&h);});
  if(ok)__atomic_fetch_add(&native_ufs_pinned_verified_blocks,1,__ATOMIC_RELAXED);
  return ok;
}
#endif
