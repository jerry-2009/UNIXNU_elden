// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
#include <stddef.h>

// These pins describe the unmodified, owned 21H461 raw filesystem images.
// The kernel containing the pins is authenticated by the existing AVB chain.
// Hash each complete image before publishing, then check every 4KiB read
// against the derived, read-only hash table. Never accept a hash from disk.
struct EldenRootPin {
  const char *name;
  uint64_t bytes;
  const char *sha256;
  const char *volumeUuid;
};
static const EldenRootPin kEldenRootPins[2] = {
  {"OS",6077546496ULL,"d8808bea18b949142b3e47bbcb780c3f22faaacd9b40a88f77c23557181edc9c","04769D26-2CA0-4825-B443-E2E5F88300F2"},
  {"SystemOS",3303014400ULL,"b4908cde41d23e6bc05e6af51a2c9eeb00cf0f863a6a18b1600c96a3fd70414f","8846FE78-2910-4297-AF97-D59BB6F8FC16"}
};
static inline bool eldenPinString(const char *a,const char *b) {
  if(!a||!b)return false;
  while(*a&&*a==*b){++a;++b;}return *a==*b;
}
static inline int eldenRootPinIndex(const char *name,uint64_t bytes) {
  for(unsigned i=0;i<2;i++)if(bytes==kEldenRootPins[i].bytes&&eldenPinString(name,kEldenRootPins[i].name))return (int)i;
  return -1;
}
static inline bool eldenPinnedMediaProof(unsigned index,const char *uuid,bool ancestry,bool sealed,bool readonly) {
  return index<2&&ancestry&&sealed&&readonly&&eldenPinString(uuid,kEldenRootPins[index].volumeUuid);
}
static inline bool eldenPinDigest(const uint8_t d[32],const char *hex) {
  static const char digits[]="0123456789abcdef";
  unsigned mismatch=0;
  for(unsigned i=0;i<32;i++){mismatch|=digits[d[i]>>4]^hex[2*i];mismatch|=digits[d[i]&15]^hex[2*i+1];}
  return mismatch==0;
}
enum EldenPinError { EldenPinOk, EldenPinGeometry, EldenPinAllocation, EldenPinRead,
  EldenPinWholeHash, EldenPinProtect };

template<class IO>
static EldenPinError eldenVerifyPinnedImage(const EldenRootPin &pin,IO &io,uint8_t *scratch,size_t capacity) {
  if(!scratch||capacity<4096||capacity%4096||!pin.bytes||pin.bytes%4096||pin.bytes/4096>UINT64_MAX/32)
    return EldenPinGeometry;
  if(!io.allocate(pin.bytes/4096*32))return EldenPinAllocation;
  typename IO::Hash whole;io.init(whole);
  for(uint64_t at=0;at<pin.bytes;){
    size_t n=pin.bytes-at<capacity?(size_t)(pin.bytes-at):capacity;
    if(!io.read(at,n,scratch)){io.discard();return EldenPinRead;}
    io.update(whole,scratch,n);
    for(size_t i=0;i<n;i+=4096)io.hash(scratch+i,4096,io.leaf((at+i)/4096));
    at+=n;io.progress(at,pin.bytes);
  }
  uint8_t digest[32];io.final(whole,digest);
  if(!eldenPinDigest(digest,pin.sha256)){io.discard();return EldenPinWholeHash;}
  if(!io.protect()){io.discard();return EldenPinProtect;}
  return EldenPinOk;
}

template<class Hash>
static bool eldenVerifyPinnedBlock(const uint8_t *table,uint64_t blocks,uint64_t index,
                                  const void *data,size_t bytes,Hash hash) {
  if(!table||!data||bytes!=4096||index>=blocks)return false;
  uint8_t digest[32];hash(data,bytes,digest);unsigned mismatch=0;
  for(unsigned i=0;i<32;i++)mismatch|=digest[i]^table[index*32+i];
  return mismatch==0;
}
