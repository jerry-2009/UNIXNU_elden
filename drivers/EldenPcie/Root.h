/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "Phy.h"
#ifdef __cplusplus
extern "C" {
#endif
enum {EldenPcieGcc,EldenPcieTcsr,EldenPcieParf,EldenPciePhyWindow,EldenPcieDbi,EldenPcieAtu,EldenPcieConfig,EldenPcieWindowCount};
enum {EldenPcieRootIdle,EldenPcieRootWorking,EldenPcieRootEndpointVisible,EldenPcieRootRefused,EldenPcieRootHeld};
enum {EldenPcieStagePins=1,EldenPcieStagePower,EldenPcieStageClocks,EldenPcieStageParf,EldenPcieStagePhy,
      EldenPcieStageSid,EldenPcieStageRoot,EldenPcieStagePerst,EldenPcieStageLink,EldenPcieStageConfig,EldenPcieStageVisible};
typedef struct {
    void *context;
    /* epoch0: matched board/cold owner/stop/fresh power gates. Nonzero: also
     * real provisional WLAN lease and stable root supplies/NoC/PLL parents. */
    int (*admit)(void *,uint64_t epoch);
    /* Electrical PERST102 + CLKREQ103 setup/readback; false asserts PERST.
     * Power-up runs only after this has actually held the endpoint in reset. */
    int (*pins)(void *,bool perst_high);
    /* Real WLAN lease + PHY supplies + interconnect/corner votes for Gen1..3.
     * Gen3 needs the board's NOM256 CX/MX budget and100MHz rate-change clock.
     * No constant-success callback is a valid native implementation. */
    int (*power_up)(void *,unsigned max_gen,uint64_t *wlan_epoch);
    int (*gcc_gate)(void *,bool acquire); /* existing shared GCC owner, not a second lock */
    int (*read)(void *,unsigned window,uint32_t offset,uint32_t *);
    int (*write)(void *,unsigned window,uint32_t offset,uint32_t);
    uint64_t (*now_us)(void *);
    void (*delay_us)(void *,unsigned);
} EldenPcieRootIo;
typedef struct {
    EldenPcieRootIo io;
    EldenPciePhy phy;
    uint64_t epoch,perst_low_us;
    unsigned state,stage,max_gen,writes,last_window;
    uint32_t last_offset,last_value,root_id,endpoint_id,root_pcie_cap,link_status;
    int error;
    bool controls_started,gcc_held,clocks_ready,perst_high;
} EldenPcieRoot;
/* Zero-initialize once; caller serializes the whole cold transaction. On any
 * uncertain operation retain mappings/votes/held GCC gate until recovery.
 * No DMA/SMMU/BAR allocation or endpoint bus-master enable is performed. */
int elden_pcie_root_start(EldenPcieRoot *,unsigned max_gen);
int elden_pcie_config_read32(EldenPcieRoot *,uint32_t offset,uint32_t *value);
uint64_t elden_pcie_window_base(unsigned window);
uint32_t elden_pcie_window_bytes(unsigned window);
#ifdef __cplusplus
}
#endif
