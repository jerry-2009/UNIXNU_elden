// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../EldenBootProperties.h"
int main(void){
  ELDEN_BOOT_PROPERTIES fdt,parent,parsed;
  const char *f="console=ttynull androidboot.bootdevice=old androidboot.slot_suffix=_a androidboot.dynamic_partitions=true";
  const char *p="androidboot.slot_suffix = \"_b\" # current slot\nandroidboot.bootdevice=1d84000.ufshc\nandroidboot.mode=normal\n";
  const char *base="androidboot.usbcontroller=a600000.dwc3\nandroidboot.mode=recovery\nandroidboot.force_normal_boot=0\n";
  assert(!EldenParseBootProperties(f,strlen(f),1,&fdt));
  assert(!EldenParseBootProperties(p,strlen(p),0,&parent));
  char added[4096];size_t bytes=0;unsigned mask=0,missing=0;
  assert(!EldenAppendBootProperties(&fdt,&parent,base,strlen(base),"rdinit=/init",12,added,sizeof(added),&bytes,&mask,&missing));
  assert(mask==0x15&&missing==0&&bytes==strlen(added));
  assert(strstr(added,"androidboot.slot_suffix=_b\n")&&strstr(added,"androidboot.bootdevice=1d84000.ufshc\n"));
  assert(!strstr(added,"mode=")&&!strstr(added,"usbcontroller="));
  assert(EldenAppendBootProperties(&fdt,&parent,base,strlen(base),"",0,added,2,&bytes,&mask,&missing)==-3);
  const char *arg="androidboot.bootdevice=explicit androidboot.slot_suffix=_a";
  assert(!EldenAppendBootProperties(&fdt,&parent,base,strlen(base),arg,strlen(arg),added,sizeof(added),&bytes,&mask,&missing));
  assert(mask==0x10&&!strstr(added,"slot_suffix")&&!strstr(added,"bootdevice="));
  const char *conflict="androidboot.usbcontroller=other";
  assert(EldenAppendBootProperties(&fdt,&parent,base,strlen(base),conflict,strlen(conflict),added,sizeof(added),&bytes,&mask,&missing)==-2);
  const char *bad[]={"androidboot.slot_suffix=_c\n","androidboot.bootdevice=a;reboot\n", "androidboot {\n slot_suffix=_a\n}\n", "androidboot.slot_suffix=_a\nandroidboot.slot_suffix=_b\n"};
  for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i)assert(EldenParseBootProperties(bad[i],strlen(bad[i]),0,&parsed)<0);
  const char *quoted="label=\"androidboot.slot_suffix=_b hidden\" console=tty0";
  assert(!EldenParseBootProperties(quoted,strlen(quoted),1,&parsed)&&!parsed.Present);
  const char *comment="# unbalanced quote \" in a comment\nandroidboot.slot_suffix=_a\n";
  assert(!EldenParseBootProperties(comment,strlen(comment),0,&parsed)&&parsed.Present==4);
  const char mixed[]="androidboot.slot_suffix=_a\0trailing";
  assert(EldenParseBootProperties(mixed,sizeof(mixed),0,&parsed)<0);
  assert(!EldenParseBootProperties(NULL,0,0,&parsed)&&parsed.Present==0);
  assert(EldenParseBootProperties(base,65537,0,&parsed)<0);
  const char *cross="androidboot.slot=a\nandroidboot.slot_suffix=_b\n";
  assert(!EldenParseBootProperties(cross,strlen(cross),0,&parent));
  assert(EldenAppendBootProperties(&fdt,&parent,base,strlen(base),"",0,added,sizeof(added),&bytes,&mask,&missing)==-2);
  puts("PASS: property precedence, explicit overrides, recovery preservation, bounds and conflicting/malformed source rejection");
}
