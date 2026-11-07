/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once
#include <Uefi.h>
#include "Generated/EldenUfsSession.h"
#include "Generated/EldenFdtHandoff.h"
typedef struct {
    struct elden_ufs_session Session;
    ELDEN_FDT_HANDOFF Fdt;
    EFI_PHYSICAL_ADDRESS Arena;
    UINTN CacheLine;
    UINT64 CounterFrequency;
    BOOLEAN Allocated;
} ELDEN_UFS_HARDWARE;
EFI_STATUS EldenUfsHardwareOpen(EFI_HANDLE SourceVolume, ELDEN_UFS_HARDWARE *Hardware);
EFI_STATUS EldenUfsHardwareClose(ELDEN_UFS_HARDWARE *Hardware);
