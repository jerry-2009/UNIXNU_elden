// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef ELDEN_FDT_HANDOFF_H
#define ELDEN_FDT_HANDOFF_H
#include <Uefi.h>
typedef struct {
  EFI_PHYSICAL_ADDRESS Copy;
  UINTN Pages;
  VOID *Previous;
  BOOLEAN Installed;
} ELDEN_FDT_HANDOFF;
EFI_STATUS EldenPrepareFdt (EFI_HANDLE Volume, ELDEN_FDT_HANDOFF *State);
EFI_STATUS EldenReleaseFdt (ELDEN_FDT_HANDOFF *State);
// Copies bounded current-boot data. NOT_FOUND is an absent source; malformed
// referenced data returns an error. Callers own the returned pool allocation.
EFI_STATUS EldenCopyChosenBootArgs (CHAR8 **Text, UINTN *Bytes);
EFI_STATUS EldenCopyOriginalBootconfig (CHAR8 **Text, UINTN *Bytes);
EFI_STATUS EldenPrintFreeMemory (VOID);
#endif
