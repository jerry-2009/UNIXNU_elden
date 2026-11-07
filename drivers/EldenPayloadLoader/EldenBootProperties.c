// SPDX-License-Identifier: BSD-2-Clause-Patent
#include "EldenBootProperties.h"
#ifdef ELDEN_BOOT_HOST_TEST
#include <string.h>
#define CLEAR(p,n) memset((p),0,(n))
#define COPY(d,s,n) memcpy((d),(s),(n))
#else
#include <Library/BaseMemoryLib.h>
#define CLEAR(p,n) ZeroMem((p),(n))
#define COPY(d,s,n) CopyMem((d),(s),(n))
#endif
static const char *const Keys[ELDEN_BOOT_PROPERTY_COUNT]={
  "androidboot.bootdevice","androidboot.boot_devices","androidboot.slot_suffix","androidboot.slot",
  "androidboot.dynamic_partitions","androidboot.usbcontroller","androidboot.usb.dwc3_msm","androidboot.hardware.platform"};
static ELDEN_SIZE length(const char *s){ELDEN_SIZE n=0;while(s[n])++n;return n;}
static int same(const char *a,const char *b,ELDEN_SIZE n){for(ELDEN_SIZE i=0;i<n;++i)if(a[i]!=b[i])return 0;return 1;}
static int whitespace(char c){return c==' '||c=='\t'||c=='\r'||c=='\n';}
static int safe_value(char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.'||c=='/'||c==':'||c==',';}

static int parse_one(const char *text,ELDEN_SIZE bytes,ELDEN_BOOT_PROPERTIES *out)
{
  ELDEN_SIZE at=0,first,key_end,last;
  while(at<bytes&&whitespace(text[at]))++at;
  if(at==bytes||text[at]=='#')return 0;
  first=at;while(at<bytes&&!whitespace(text[at])&&text[at]!='=')++at;key_end=at;
  unsigned key;
  for(key=0;key<ELDEN_BOOT_PROPERTY_COUNT;++key)
    if(length(Keys[key])==key_end-first&&same(Keys[key],text+first,key_end-first))break;
  if(key==ELDEN_BOOT_PROPERTY_COUNT)return 0;
  while(at<bytes&&whitespace(text[at]))++at;
  if(at==bytes||text[at++]!='=')return -1;
  while(at<bytes&&whitespace(text[at]))++at;
  first=at;last=bytes;
  while(last>first&&whitespace(text[last-1]))--last;
  if(first<last&&text[first]=='"'){
    if(last-first<2||text[last-1]!='"')return -1;
    ++first;--last;
  }
  if(last==first||last-first>=ELDEN_BOOT_VALUE_BYTES)return -1;
  for(ELDEN_SIZE i=first;i<last;++i)if(!safe_value(text[i]))return -1;
  if(key==2&&(last-first!=2||text[first]!='_'||(text[first+1]!='a'&&text[first+1]!='b')))return -1;
  if(key==3&&(last-first!=1||(text[first]!='a'&&text[first]!='b')))return -1;
  if(key==4&&!((last-first==4&&same(text+first,"true",4))||(last-first==5&&same(text+first,"false",5))))return -1;
  if(out->Present&(1U<<key)){
    if(length(out->Value[key])!=last-first||!same(out->Value[key],text+first,last-first))return -2;
    return 0;
  }
  COPY(out->Value[key],text+first,last-first);out->Value[key][last-first]=0;out->Present|=1U<<key;
  return 0;
}

int EldenParseBootProperties(const char *text,ELDEN_SIZE bytes,int format,ELDEN_BOOT_PROPERTIES *out)
{
  if(!out||(!text&&bytes)||bytes>65536||(format!=0&&format!=1))return -1;
  CLEAR(out,sizeof(*out));
  ELDEN_SIZE at=0;
  while(at<bytes){
    while(at<bytes&&whitespace(text[at]))++at;
    if(at==bytes)break;
    if(text[at]==0){while(at<bytes)if(text[at++]!=0)return -1;break;}
    ELDEN_SIZE first=at,comment_end=(ELDEN_SIZE)-1;char quote=0;
    while(at<bytes&&text[at]){
      char c=text[at];
      if(!format&&c=='\n')break;
      if(format&&!quote&&whitespace(c))break;
      if(!format&&!quote&&(c=='{'||c=='}'))return -1;
      if(!format&&!quote&&c=='#'){
        comment_end=at;while(at<bytes&&text[at]&&text[at]!='\n')++at;break;
      }
      if(c=='"'||c=='\''){if(!quote)quote=c;else if(quote==c)quote=0;}
      ++at;
    }
    if(quote)return -1;
    int result=parse_one(text+first,(comment_end==(ELDEN_SIZE)-1?at:comment_end)-first,out);if(result)return result;
    if(at<bytes&&text[at])++at;
  }
  return 0;
}

int EldenAppendBootProperties(const ELDEN_BOOT_PROPERTIES *fdt,const ELDEN_BOOT_PROPERTIES *parent,
  const char *base,ELDEN_SIZE base_bytes,const char *args,ELDEN_SIZE arg_bytes,
  char *added,ELDEN_SIZE capacity,ELDEN_SIZE *added_bytes,unsigned *added_mask,unsigned *missing_mask)
{
  ELDEN_BOOT_PROPERTIES own,command;
  if(!fdt||!parent||!added||!capacity||!added_bytes||!added_mask||!missing_mask)return -1;
  *added_bytes=0;*added_mask=0;*missing_mask=0;added[0]=0;
  int result=EldenParseBootProperties(base,base_bytes,0,&own);if(result)return result;
  result=EldenParseBootProperties(args,arg_bytes,1,&command);if(result)return result;
  unsigned present=own.Present|command.Present;
  const char *effective_slot=0,*effective_suffix=0;
  for(unsigned i=2;i<=3;++i){
    unsigned bit=1U<<i;
    const char *value=(own.Present&bit)?own.Value[i]:(command.Present&bit)?command.Value[i]:
      (parent->Present&bit)?parent->Value[i]:(fdt->Present&bit)?fdt->Value[i]:0;
    if(i==2)effective_suffix=value;else effective_slot=value;
  }
  if(effective_slot&&effective_suffix&&effective_slot[0]!=effective_suffix[1])return -2;
  for(unsigned i=0;i<ELDEN_BOOT_PROPERTY_COUNT;++i){
    unsigned bit=1U<<i;
    if((own.Present&command.Present&bit)&&
       (length(own.Value[i])!=length(command.Value[i])||!same(own.Value[i],command.Value[i],length(own.Value[i]))))return -2;
    if(present&bit)continue;
    const char *value=(parent->Present&bit)?parent->Value[i]:(fdt->Present&bit)?fdt->Value[i]:0;
    if(!value)continue;
    ELDEN_SIZE key_bytes=length(Keys[i]),value_bytes=length(value),need=key_bytes+value_bytes+2;
    if(*added_bytes>=capacity||need>=capacity-*added_bytes)return -3;
    COPY(added+*added_bytes,Keys[i],key_bytes);*added_bytes+=key_bytes;added[(*added_bytes)++]='=';
    COPY(added+*added_bytes,value,value_bytes);*added_bytes+=value_bytes;added[(*added_bytes)++]='\n';
    added[*added_bytes]=0;*added_mask|=bit;present|=bit;
  }
  *missing_mask=0x15U&~present; // bootdevice, slot_suffix, dynamic_partitions
  return 0;
}
