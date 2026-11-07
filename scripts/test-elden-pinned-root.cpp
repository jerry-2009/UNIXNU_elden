// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "driver-patches/EldenPinnedRoot.h"
#include <openssl/sha.h>
#include <vector>
#include <string>
#include <cstdio>
#include <cstring>
#include <cassert>
struct IO {
  using Hash=SHA256_CTX;
  std::vector<uint8_t> bytes,table;
  FILE *file=nullptr;uint64_t base=0;
  bool readFail=false,protectFail=false,sealed=false,discarded=false;
  bool allocate(uint64_t n){table.resize(n);return true;}
  uint8_t *leaf(uint64_t n){assert(n*32+32<=table.size());return table.data()+n*32;}
  static void init(Hash &h){SHA256_Init(&h);}
  static void update(Hash &h,const void *p,size_t n){SHA256_Update(&h,p,n);}
  static void final(Hash &h,uint8_t *d){SHA256_Final(d,&h);}
  static void hash(const void *p,size_t n,uint8_t *d){SHA256((const unsigned char*)p,n,d);}
  bool read(uint64_t at,size_t n,void *p){
    if(readFail)return false;
    if(file){if(fseeko(file,base+at,SEEK_SET))return false;return fread(p,1,n,file)==n;}
    if(at>bytes.size()||n>bytes.size()-at)return false;memcpy(p,bytes.data()+at,n);return true;
  }
  void progress(uint64_t,uint64_t){}
  void discard(){table.clear();discarded=true;sealed=false;}
  bool protect(){if(protectFail)return false;sealed=true;return true;}
};
int main(int argc,char **argv){
  uint8_t scratch[65536],d[32];IO fixture;fixture.bytes.resize(3*4096);
  for(size_t i=0;i<fixture.bytes.size();i++)fixture.bytes[i]=(uint8_t)(i*37+(i>>8));
  IO::hash(fixture.bytes.data(),fixture.bytes.size(),d);char hex[65];for(unsigned i=0;i<32;i++)sprintf(hex+2*i,"%02x",d[i]);
  EldenRootPin pin={"fixture",fixture.bytes.size(),hex,"unused"};
  assert(eldenVerifyPinnedImage(pin,fixture,scratch,sizeof(scratch))==EldenPinOk&&fixture.sealed);
  for(unsigned i=0;i<3;i++)assert(eldenVerifyPinnedBlock(fixture.table.data(),3,i,fixture.bytes.data()+i*4096,4096,IO::hash));
  assert(!eldenVerifyPinnedBlock(fixture.table.data(),3,3,fixture.bytes.data(),4096,IO::hash));
  assert(!eldenVerifyPinnedBlock(fixture.table.data(),3,0,fixture.bytes.data(),4095,IO::hash));
  fixture.bytes[5000]^=1;
  assert(!eldenVerifyPinnedBlock(fixture.table.data(),3,1,fixture.bytes.data()+4096,4096,IO::hash));
  assert(eldenVerifyPinnedImage(pin,fixture,scratch,sizeof(scratch))==EldenPinWholeHash&&fixture.discarded&&!fixture.sealed);
  fixture.bytes[5000]^=1;fixture.readFail=true;fixture.discarded=false;
  assert(eldenVerifyPinnedImage(pin,fixture,scratch,sizeof(scratch))==EldenPinRead&&fixture.discarded);
  fixture.readFail=false;fixture.protectFail=true;fixture.discarded=false;
  assert(eldenVerifyPinnedImage(pin,fixture,scratch,sizeof(scratch))==EldenPinProtect&&fixture.discarded&&!fixture.sealed);
  assert(eldenRootPinIndex("OS",6077546496ULL)==0);
  assert(eldenRootPinIndex("SystemOS",3303014400ULL)==1);
  assert(eldenRootPinIndex("userdata",6077546496ULL)==-1);
  assert(eldenRootPinIndex("OS",6077546495ULL)==-1);
  assert(eldenPinnedMediaProof(0,kEldenRootPins[0].volumeUuid,true,true,true));
  assert(!eldenPinnedMediaProof(0,kEldenRootPins[1].volumeUuid,true,true,true));
  assert(!eldenPinnedMediaProof(2,kEldenRootPins[0].volumeUuid,true,true,true));
  assert(!eldenPinnedMediaProof(0,kEldenRootPins[0].volumeUuid,false,true,true));
  assert(!eldenPinnedMediaProof(0,kEldenRootPins[0].volumeUuid,true,false,true));
  assert(!eldenPinnedMediaProof(0,kEldenRootPins[0].volumeUuid,true,true,false));
  puts("Fixture integrity, range, corruption, read failure and protection failure checks passed.");
  if(argc==2){
    FILE *f=fopen(argv[1],"rb");assert(f);uint64_t offsets[]={1048576ULL,6078595072ULL};
    for(unsigned i=0;i<2;i++){
      IO io;io.file=f;io.base=offsets[i];auto &p=kEldenRootPins[i];
      assert(eldenVerifyPinnedImage(p,io,scratch,sizeof(scratch))==EldenPinOk&&io.sealed);
      uint64_t count=p.bytes/4096,points[]={0,count/2,count-1};
      for(auto index:points){assert(io.read(index*4096,4096,scratch));assert(eldenVerifyPinnedBlock(io.table.data(),count,index,scratch,4096,IO::hash));scratch[23]^=1;assert(!eldenVerifyPinnedBlock(io.table.data(),count,index,scratch,4096,IO::hash));}
      printf("%s full-image pin + first/middle/last block integrity passed (%zu table bytes).\n",p.name,io.table.size());fflush(stdout);
    }
    fclose(f);
  }
  return 0;
}
