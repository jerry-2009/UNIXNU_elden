/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {uint16_t offset;uint8_t value;uint16_t delay_us;} EldenPciePhyWrite;
enum {EldenPciePhyIdle,EldenPciePhyProgramming,EldenPciePhyReady,EldenPciePhyRefused,EldenPciePhyHeld};
typedef struct {
    void *context;
    /* Must verify the current WLAN lease, owned PERST# low, required rails,
     * GDSCs/clocks and exclusive cold-bringup ownership before ANY MMIO.
     * This component separately checks initial PCS reset, then releases it.
     * During programming it also closes admission on a stop request. Never
     * substitute a constant-success callback for these native prerequisites. */
    int (*admit)(void *,uint64_t epoch);
    int (*read)(void *,uint16_t offset,uint32_t *);
    int (*write)(void *,uint16_t offset,uint32_t value);
    int (*pipe_to_phy)(void *); /* real select + acknowledgement */
    uint64_t (*now_us)(void *);
    void (*delay_us)(void *,unsigned);
} EldenPciePhyIo;
typedef struct {
    EldenPciePhyIo io;
    uint64_t epoch;
    unsigned state,writes,last_index,polls;
    int error;
    uint32_t status;
} EldenPciePhy;
/* One cold bring-up transaction. Caller serializes with root-complex shutdown
 * and retains maps after any uncertain write. No retry/reset/rail operation.
 * Ready means PHY status only, not PCIe link/endpoint/DMA readiness. */
int elden_pcie_phy_start(EldenPciePhy *,uint64_t epoch);
#ifdef __cplusplus
}
#endif
