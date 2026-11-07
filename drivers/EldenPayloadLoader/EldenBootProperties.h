// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#ifdef ELDEN_BOOT_HOST_TEST
#include <stddef.h>
typedef size_t ELDEN_SIZE;
#else
#include <Uefi.h>
typedef UINTN ELDEN_SIZE;
#endif
#define ELDEN_BOOT_PROPERTY_COUNT 8
#define ELDEN_BOOT_VALUE_BYTES 256
typedef struct {
  char Value[ELDEN_BOOT_PROPERTY_COUNT][ELDEN_BOOT_VALUE_BYTES];
  unsigned Present;
} ELDEN_BOOT_PROPERTIES;
// Format: 0 = flat bootconfig lines, 1 = kernel command-line tokens.
// Returns 0, or negative for malformed/conflicting recognized properties.
int EldenParseBootProperties(const char *Text,ELDEN_SIZE Bytes,int Format,ELDEN_BOOT_PROPERTIES *Out);
// Original bootconfig takes precedence over FDT. Existing final bootconfig or
// explicit command-line properties are preserved, never silently overridden.
int EldenAppendBootProperties(const ELDEN_BOOT_PROPERTIES *Fdt,const ELDEN_BOOT_PROPERTIES *Parent,
  const char *Base,ELDEN_SIZE BaseBytes,const char *Arguments,ELDEN_SIZE ArgumentBytes,
  char *Added,ELDEN_SIZE Capacity,ELDEN_SIZE *AddedBytes,unsigned *AddedMask,unsigned *MissingMask);
