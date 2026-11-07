// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
// SM8750 USB resources cross-checked against elden Linux DTS/GCC and dwc3-qcom.
// Long/short-port selection, PHY and regulator ownership remain with firmware.
#define ELDEN_USB_GCC_PHYS       0x139000ULL
#define ELDEN_USB_GCC_BYTES      0x1000U
#define ELDEN_USB_GDSCR          0x04U
#define ELDEN_USB_MASTER_CLK     0x18U
#define ELDEN_USB_CFG_CLK        0x8cU
#define ELDEN_USB_AGGRE_CLK      0x90U
#define ELDEN_USB_DWC_PHYS       0x0a600000ULL
#define ELDEN_USB_DWC_BYTES      0xe000U
#define ELDEN_USB_SMMU_PHYS      0x15000000ULL
#define ELDEN_USB_SMMU_BYTES     0x100000U
#define ELDEN_USB_SID            0x40U
#define ELDEN_USB_QSCRATCH_PHYS  0x0a6f8800ULL
#define ELDEN_USB_QSCRATCH_BYTES 0x100U
