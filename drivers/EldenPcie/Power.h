/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#include "Sm8750Rpmh.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {uint16_t mv;uint8_t type,subtype,status,enable,mode;} EldenPcieRail;
typedef struct {
    Sm8750RpmhCmd commands[10];
    uint32_t count,wait_mask,max_gen;
    uint32_t mx_index,cx_index,mx_level,cx_level;
    uint32_t sn4_minimum,sn4_applied,sn4_unit;
    uint16_t sn4_width,rail_mv[2];
    uint8_t sn4_vcd,sh1_vcd;
} EldenPciePowerPlan;
/* Only an explicit bounded bring-up policy currently exists: unknown APPS
 * boot votes cannot be read back. ARC table maxima and saturated SN4 avoid
 * lowering such votes; SH1 is boolean enable. No MC0/ACV/GPU vote is emitted.
 * This is NOT a daily power-saving policy and must not be enabled by default.
 * Retain successful votes until platform reset; no guessed restoration. */
enum {EldenPciePowerFullOnDiagnostic=1};
int elden_pcie_power_plan(const Sm8750CmdDb *,const EldenPcieRail before[2],const uint16_t retained_mv[2],unsigned max_gen,unsigned policy,EldenPciePowerPlan *);
/* Provisional WLAN lease is sufficient here; endpoint cannot identify itself
 * before root power/link. Native implementation checks explicit boot intent. */
int elden_wlan_root_power(const void *provider,uint64_t epoch,unsigned max_gen);
#ifdef __cplusplus
}
#endif
