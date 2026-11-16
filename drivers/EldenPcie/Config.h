/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    void *context;
    int (*admit)(void *,bool cleanup); /* same native owner; cleanup retains maps/power */
    int (*read32)(void *,uint32_t,uint32_t *);
    int (*write32)(void *,uint32_t,uint32_t);
    int (*master_ready)(void *); /* real DMA/MSI/runtime and stop path; not a stub */
} EldenPcieConfigIo;
typedef struct {
    EldenPcieConfigIo io;
    uint64_t sink;
    uint32_t pcie_cap,msi_cap,msi_header,command,reads,writes;
    int error;
    bool attempted,ready,master_attempted,master_known;
    uint32_t initial_link_control;
    bool link_control_saved;
} EldenPcieConfigAccess;
/* Serialized PCIe owner. No generic PCI enumerator: the cold, CPU-identified
 * Peach endpoint and its fixed owned MSI sink are mandatory. */
int elden_pcie_cfg_open(EldenPcieConfigAccess *,uint64_t owned_sink);
int elden_pcie_cfg_read(EldenPcieConfigAccess *,int offset,int size,uint32_t *,bool cleanup);
int elden_pcie_cfg_write(EldenPcieConfigAccess *,int offset,int size,uint32_t,bool cleanup);
/* BM is never writable through the generic config callback. Set attempted
 * before a possible enabling write so failed readback cannot imply no DMA. */
int elden_pcie_cfg_master(EldenPcieConfigAccess *,bool enable);
#ifdef __cplusplus
}
#endif
