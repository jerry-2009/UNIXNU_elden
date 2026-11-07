// SPDX-License-Identifier: BSD-2-Clause-Patent
// Bridge the existing owner SystemOS/Data startup hooks to the authenticated
// UFS windows. UUID alone is never sufficient: live ancestry and sealed hashes
// must identify one of this kernel's two pinned, read-only providers.
#if defined(ELDEN_PINNED_ROOT) && ELDEN_PINNED_ROOT
#include <libkern/c++/OSBoolean.h>
#include <sys/types.h>
static bool eldenPinnedMedia(IORegistryEntry *media,int *index,dev_t *device,char *path,size_t size) {
  OSString *uuid=OSDynamicCast(OSString,media->getProperty("UUID"));
  OSString *bsd=OSDynamicCast(OSString,media->getProperty(kIOBSDNameKey));
  OSNumber *majorValue=OSDynamicCast(OSNumber,media->getProperty(kIOBSDMajorKey));
  OSNumber *minorValue=OSDynamicCast(OSNumber,media->getProperty(kIOBSDMinorKey));
  OSBoolean *writable=OSDynamicCast(OSBoolean,media->getProperty("Writable"));
  if(!uuid||!bsd||!majorValue||!minorValue||!writable||writable->isTrue()||
     majorValue->unsigned64BitValue()>255||minorValue->unsigned64BitValue()>0xffffff)return false;
  for(unsigned i=0;i<2;i++) {
    const EldenPinnedState &pin=gEldenPinned[i];
    if(!pin.owner||!__atomic_load_n(&pin.sealed,__ATOMIC_ACQUIRE)||
       strcmp(uuid->getCStringNoCopy(),kEldenRootPins[i].volumeUuid))continue;
    IORegistryIterator *parents=IORegistryIterator::iterateOver(media,gIOServicePlane,
      kIORegistryIterateRecursively|kIORegistryIterateParents);
    bool belongs=parents&&ufsMediaHasAncestor(*parents,pin.owner);
    if(parents)parents->release();
    if(!eldenPinnedMediaProof(i,uuid->getCStringNoCopy(),belongs,pin.sealed,!writable->isTrue()))continue;
    if(path&&size){int n=snprintf(path,size,"/dev/%s",bsd->getCStringNoCopy());if(n<0||(size_t)n>=size)return false;}
    *index=(int)i;
    *device=makedev(majorValue->unsigned32BitValue(),minorValue->unsigned32BitValue());
    if(*device==NODEV)return false;
    return true;
  }
  return false;
}
static bool eldenFindPinnedMedia(dev_t requested,const char *uuid,int *index,dev_t *device,char *path,size_t size) {
  OSDictionary *matching=IOService::serviceMatching("IOMedia");
  OSIterator *iterator=matching?IOService::getMatchingServices(matching):nullptr;
  unsigned matches=0;int found=-1;dev_t selected=NODEV;char name[64]={};
  if(iterator) {
    for(unsigned n=0;n<64;n++) {
      IORegistryEntry *media=OSDynamicCast(IORegistryEntry,iterator->getNextObject());if(!media)break;
      int i;dev_t d;char candidate[64];
      if(!eldenPinnedMedia(media,&i,&d,candidate,sizeof(candidate)))continue;
      if(requested!=NODEV&&d!=requested)continue;
      if(uuid&&strcmp(uuid,kEldenRootPins[i].volumeUuid))continue;
      matches++;found=i;selected=d;strlcpy(name,candidate,sizeof(name));
    }
    iterator->release();
  }
  OSSafeReleaseNULL(matching);
  if(matches!=1)return false;
  if(path&&size){if(strlen(name)>=size)return false;strlcpy(path,name,size);}
  if(index)*index=found;if(device)*device=selected;return true;
}
extern "C" int native_verified_block_volume_device(const char *uuid,dev_t *device,char *path,size_t size) {
  if(!uuid||!device||!path||!size)return 0;
  return eldenFindPinnedMedia(NODEV,uuid,nullptr,device,path,size)?1:0;
}
extern "C" int native_verified_block_root_authorized(dev_t device) {
  return device!=NODEV&&eldenFindPinnedMedia(device,nullptr,nullptr,nullptr,nullptr,0)?1:0;
}
extern "C" int native_verified_block_manifest_sha384(dev_t device,const char *uuid,uint8_t digest[48]) {
  int index=-1;
  if(!uuid||!digest||device==NODEV||!eldenFindPinnedMedia(device,uuid,&index,nullptr,nullptr,0))return 0;
  static const char domain[]="EldenPinnedImage.OwnerKernel.v1";
  const EldenRootPin &pin=kEldenRootPins[index];
  SHA384_CTX h;SHA384_Init(&h);SHA384_Update(&h,domain,sizeof(domain));
  SHA384_Update(&h,pin.sha256,64);SHA384_Update(&h,pin.volumeUuid,36);
  SHA384_Update(&h,&pin.bytes,sizeof(pin.bytes));SHA384_Final(digest,&h);
  return 1;
}
#endif
