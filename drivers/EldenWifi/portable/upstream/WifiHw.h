// SPDX-License-Identifier: BSD-2-Clause-Patent
// piano (Xiaomi Pad 8 Pro, SM8750) facts for the WCN7860 Wi-Fi path, as PianoWifi's level 1 survey reads them. Sources (facts only,
// no code, comment or table copied from any of them):
//   DT   = out/inputs/piano-boot.dtb, the running Ubuntu DT (dtc -I dtb -O dts): pcie@1c00000 and its pcie@0/wifi@0, phy@1c06000,
//          wcn7860-pmu, pinctrl@f100000 (wlan-en-state, pcie0-default-state), spmi@c400000 pmic@5/gpio@8800 (bt-en-default-state),
//          rsc@16500000 regulators-1..5, aop-cmd-db@81c60000, iommu@15000000
//   GCC  = mainline drivers/clk/qcom/gcc-sm8750.c and include/dt-bindings/clock/qcom,sm8750-gcc.h (register offsets, vote bits)
//   TCSR = mainline drivers/clk/qcom/tcsrcc-sm8750.c (tcsr_pcie_0_clkref_en)
//   PCI  = mainline drivers/pci/controller/dwc/pcie-qcom.c (cfg_1_9_0, the SM8550 data SM8750 falls back to), pcie-designware.h
//   PHY  = mainline drivers/phy/qualcomm/phy-qcom-qmp-pcie.c (sm8750_qmp_gen3x2_pciephy_cfg: qmp_pcie_offsets_v7), phy-qcom-qmp-pcs-v7.h
//   SHENG = UniXNU-sheng package/WifiProbe.cpp (BSD-2-Clause-Patent; SM8550 + WCN7850, hardware-verified there): which reads are
//          safe when (a block whose power domain or interface clock is off stalls the bus), the TLMM pin layout, the SMPS page rule
//   PAGANI = UniXNU-Pagani-Drivers drivers/PaganiWifi/PaganiWifiTables.h (BSD-2-Clause-Patent, 3d570b7; SM8750 + the same 17cb:110e
//          chip on the OnePlus 13T, host-tested only): the same GCC/PARF/PHY/TCSR offsets as mainline, the PMIC LDO page rule, hwcg
// docs/drivers/wifi.md section 2 has the same facts with their state (verified / inferred / needs-boot).
#pragma once
#include <stddef.h>
#include <stdint.h>
#if __has_include(<new>)
#include <new>
#else
// The kernel has no <new>: XNU's own forward declaration (libkern/c++/safe_allocation.h). The reserved placement form, which the
// compiler emits as its pointer argument (no call, no import).
void *operator new(size_t, void *) noexcept;
#endif

namespace pianowifi {

// A value reset in place. `x = T{}` builds the fresh T on the stack first and copies it over: with Link (the scan list,
// about 12 KiB) and HttRx (the buffers' addresses, about 13 KiB) inlined into level 6, the ladder's 16 KiB kernel stack
// overflowed as level 6 began (boots 10c, 10d and 10d-ctl, 2026-11-14: "Invalid kernel stack pointer (probable overflow)" in
// the mailbox). Every whole-object reset of this package is renew() for that reason.
template <class T>
inline void renew(T &x)
{
  x.~T();
  ::new (static_cast<void *>(&x)) T();
}

// ---- PCIe0 root complex (DT pcie@1c00000, qcom,pcie-sm8750 + qcom,pcie-sm8550, num-lanes 2, linux,pci-domain 0) ----
// reg: parf 0x1c00000+0x3000, dbi 0x40000000+0xf1d, elbi 0x40000f20+0xa8, atu 0x40001000+0x1000, config 0x40100000+0x100000,
// mhi 0x1c03000+0x1000. ranges: I/O 0x40200000+1 MiB, 32-bit memory 0x40300000+0x3d00000 (PCI = CPU address), 64-bit memory
// 0x4_0000_0000 + 0x3_0000_0000. The endpoint wifi@0 (compatible pci17cb,110e) is bus 1 device 0 below the root port (pcie@0).
constexpr uint64_t kParf = 0x01c00000, kParfBytes = 0x3000;
constexpr uint64_t kDbi = 0x40000000, kDbiBytes = 0x1000;
constexpr uint64_t kAtu = 0x40001000, kAtuBytes = 0x1000;
constexpr uint64_t kConfig = 0x40100000;   // never read by level 1 (an access through an iATU nobody programmed can abort)
constexpr uint64_t kMem32 = 0x40300000, kMem32Bytes = 0x3d00000;
constexpr uint16_t kEndpointVendor = 0x17cb, kEndpointDevice = 0x110e;
// PARF (PCI): system control, PM control, PHY control (bit 0 test power-down), LTSSM (bit 8 enable, state 5:0), interrupt status
// (bit 1 link down), status, DBI base (v2, 64-bit), slave address space size (v2), ATU base, device type (4 = root complex),
// BDF-to-SID config (bit 0 bypass). PM_STTS 0x24 is SHENG's/PAGANI's name (mainline does not define it): read for the record only.
constexpr uint32_t kParfSysCtrl = 0x00, kParfPmCtrl = 0x20, kParfPmStts = 0x24, kParfPhyCtrl = 0x40, kParfLtssm = 0x1b0,
                   kParfIntAllStatus = 0x224, kParfStatus = 0x230, kParfDbiBase = 0x350, kParfSlvSpace = 0x358,
                   kParfAtuBase = 0x634, kParfDeviceType = 0x1000, kParfBdfToSidCfg = 0x2c00;
constexpr uint32_t kParfLtssmEnable = 1u << 8;
// DBI, the root port's own configuration space (type 1 header) and the DesignWare port logic
constexpr uint32_t kDbiId = 0x00, kDbiCommand = 0x04, kDbiClass = 0x08, kDbiBusNumbers = 0x18, kDbiCapPtr = 0x34,
                   kPortDebug0 = 0x728, kPortDebug1 = 0x72c;
constexpr uint32_t kPortDebug1LinkUp = 1u << 4, kLtssmMask = 0x3f, kLtssmL0 = 0x11;
// iATU (unrolled, 0x200 per outbound region at the ATU base): control 1 at +0, control 2 at +4 (bit 31 enable), base +8/+0xc,
// limit +0x10, target +0x14/+0x18
constexpr uint32_t kAtuRegion = 0x200, kAtuCtrl2Enable = 1u << 31;

// ---- PCIe0 QMP PHY (DT phy@1c06000, qcom,sm8750-qmp-gen3x2-pcie-phy, 0x2000 bytes; power-domains gcc 1 = PCIE_0_PHY_GDSC;
// resets gcc 7 = PCIE_0_PHY_BCR; clocks aux, cfg_ahb, TCSR ref, rchng 100 MHz, pipe) ----
// The v7 layout (serdes 0x0, pcs 0x400, pcs_misc 0x800, tx 0x1000, rx 0x1200, tx2 0x1800, rx2 0x1a00; SHENG's SM8550 PHY is v6 with
// pcs at 0x200, not this one): PCS SW_RESET +0x00, PCS_STATUS1 +0x14 (bit 6 PHYSTATUS: set while the PHY is not ready),
// POWER_DOWN_CONTROL +0x40 (3 = powered), START_CONTROL +0x44 (3 = started).
constexpr uint64_t kPhy = 0x01c06000, kPhyBytes = 0x2000;
constexpr uint32_t kPcs = 0x400, kPcsSwReset = 0x00, kPcsStatus1 = 0x14, kPcsPowerDown = 0x40, kPcsStart = 0x44;
constexpr uint32_t kPcsPhyStatus = 1u << 6;

// ---- GCC (DT clock-controller@100000; mainline gcc-sm8750.c, the same values as PAGANI's table) ----
constexpr uint64_t kGcc = 0x00100000;
// Power domains: GDSCR (bit 31 PWR_ON, bit 0 SW_COLLAPSE) and CFG_GDSCR at +4 (bit 16 power-up complete, bit 15 power-down complete,
// which Linux polls: POLL_CFG_GDSCR). Both are votable through the collapse register (a set bit keeps the domain collapsed: bit 0
// PCIe0, bit 2 PCIe0 PHY). DT power-domains gcc 0 = PCIE_0_GDSC (controller), gcc 1 = PCIE_0_PHY_GDSC (phy@1c06000).
constexpr uint32_t kGccPcie0Gdsc = 0x6b004, kGccPcie0PhyGdsc = 0x6c000, kGccCollapse = 0x5214c;
constexpr uint32_t kCollapsePcie0 = 1u << 0, kCollapsePcie0Phy = 1u << 2;
// Block resets (BCR, bit 0 asserts): DT resets gcc 4 = PCIE_0_BCR (controller), gcc 7 = PCIE_0_PHY_BCR (PHY); the others for the record
struct Reset { const char *name; uint32_t bcr; };
constexpr Reset kResets[] = {{"pcie0", 0x6b000}, {"pcie0_phy", 0x6c01c}, {"link_down", 0x6c014}, {"nocsr_com_phy", 0x6c020},
                             {"phy_nocsr_com_phy", 0x6c028}, {"pcie_phy", 0x6f000}, {"phy_cfg_ahb", 0x6f00c}, {"phy_com", 0x6f010}};
constexpr unsigned kResetCount = sizeof kResets / sizeof kResets[0];
enum : unsigned { kResetPcie0 = 0, kResetPcie0Phy = 1 };
// Branch clocks (CBCR: bit 31 CLK_OFF, bit 1 HW_CTL, bit 0 CLK_ENABLE), each voted through one bit of a vote register. hwcg: the
// branch is gated by hardware when idle, so it may read CLK_OFF although it is voted (PAGANI); level 1 counts such a branch as
// running only with piano-wifi-hwcg=1 and only when its vote bit and HW_CTL are set.
struct Branch { const char *name; uint32_t cbcr; uint32_t vote; uint8_t bit; bool hwcg; };
constexpr uint32_t kGccVote8 = 0x52008, kGccVote0 = 0x52000;
constexpr Branch kBranches[] = {
  {"slv_axi", 0x6b020, kGccVote8, 0, true},           {"mstr_axi", 0x6b030, kGccVote8, 1, true},
  {"cfg_ahb", 0x6b040, kGccVote8, 2, true},           {"aux", 0x6b044, kGccVote8, 3, false},
  {"pipe", 0x6b054, kGccVote8, 4, false},             {"slv_q2a", 0x6b01c, kGccVote8, 5, false},
  {"cnoc_sf_axi", 0x10058, kGccVote8, 6, true},       {"qmip_ahb", 0x6b018, kGccVote0, 11, true},
  {"aggre_noc_axi", 0x10068, kGccVote0, 12, true},    {"ddrss_sf_qtb", 0x1007c, kGccVote0, 19, true},
  {"cfg_noc_anoc_ahb", 0x10050, kGccVote0, 20, true}, {"phy_rchng", 0x6b064, kGccVote0, 22, false},
};
constexpr unsigned kBranchCount = sizeof kBranches / sizeof kBranches[0];
enum : unsigned { kSlvAxi = 0, kMstrAxi, kCfgAhb, kAux, kPipe, kSlvQ2a, kCnocSfAxi, kQmipAhb, kAggreNoc, kDdrssSf, kCfgNocAnoc, kPhyRchng };
// RCGs (CMD_RCGR at +0: bit 0 update, bit 31 root off; CFG_RCGR at +4) and the pipe clock mux (0 = the PHY's pipe clock, 2 = TCXO)
constexpr uint32_t kGccPcie0AuxRcg = 0x6b084, kGccPcie0RchngRcg = 0x6b068, kGccPcie0PipeMux = 0x6b080;
constexpr uint32_t kGdscPwrOn = 1u << 31, kGdscSwCollapse = 1u << 0, kCbcrClkOff = 1u << 31, kCbcrHwCtl = 1u << 1, kBcrAssert = 1u << 0;

// ---- TCSR clock references (DT clock-controller@f204008; the PHY's "ref" is TCSR clock 0, tcsr_pcie_0_clkref_en, bit 0) ----
constexpr uint64_t kTcsrPcie0ClkRef = 0x0f204008;

// ---- TLMM (DT pinctrl@f100000, 0x102000 bytes, 216 pins; reserved 36-39, 48-51, 74, none of them ours) ----
// Pin n: configuration at n * 0x1000 (pull 1:0 (0 none, 1 down, 2 keeper, 3 up), function 5:2, drive 8:6 ((v + 1) * 2 mA), output
// enable 9), input (bit 0) and output (bit 1) at +4 (SHENG; the same layout PianoPower and PianoDwc3 use).
constexpr uint64_t kTlmm = 0x0f100000;
constexpr uint32_t kTlmmStride = 0x1000;
struct Pin { const char *name; unsigned gpio; };
// DT: wcn7860-pmu wlan-enable-gpios <tlmm 16 0>, swctrl-gpios <tlmm 18 0>; pcie@0 reset-gpios <tlmm 102 active-low>, wake-gpios
// <tlmm 104 active-low>; pcie0-default-state: gpio102 "gpio" pull-down (PERST#), gpio103 "pcie0_clk_req_n" pull-up, gpio104
// "gpio" pull-up (WAKE#); wlan-en-state: gpio16 "gpio" pull-down output-low. Also read, for the record (SM8750 pinctrl / PAGANI,
// not in piano's DT): gpio19 (function wcn_sw), gpio202 and gpio203 (eGPIO host/device sign of life on the 13T).
constexpr Pin kPins[] = {{"WLAN_EN", 16}, {"SW_CTRL", 18}, {"PERST#", 102}, {"CLKREQ#", 103}, {"WAKE#", 104},
                         {"gpio19", 19},  {"gpio202", 202}, {"gpio203", 203}};
constexpr unsigned kPinCount = sizeof kPins / sizeof kPins[0];
enum : unsigned { kPinWlanEn = 0, kPinSwCtrl, kPinPerst, kPinClkReq, kPinWake };

// ---- apps SMMU (DT iommu@15000000, qcom,sm8750-smmu-500): pcie@1c00000 iommu-map <0 &apps_smmu 0x1400 1>, <0x100 &apps_smmu 0x1401 1>:
// requester 0 (the root port) is stream 0x1400, requester 0x100 (bus 1, the WCN7860) is stream 0x1401 ----
constexpr uint64_t kSmmu = 0x15000000, kSmmuBytes = 0x100000;
constexpr uint16_t kStreamRoot = 0x1400, kStreamEndpoint = 0x1401;
// MSIs: msi-map <0 &its 0x1400 1>, <0x100 &its 0x1401 1> (GIC ITS 0x16040000, which XNU does not drive); the controller's own
// "msi0".."msi7" lines are GIC SPI 141-148, "global" SPI 140 (DT interrupts). Not used by level 1.

// ---- the WCN7860 PMU's supplies and the PHY's (DT), as RPMh VRM resources (cmd-db name) and the PMIC peripheral behind them ----
// The PMIC is pmic-id letter - 'a' = SPMI SID (b 1, d 3, f 5, g 6, i 8; PAGANI's PPIDs agree). SMPS n is peripheral page
// 0x9b + 3 * (n - 1) (SHENG, PAGANI); LDO n is page 0xc0 + n on PAGANI's SM8750 PMICs (from its running DT's OCP notifier names;
// piano's DT has none), 0x40 + n - 1 in SHENG's guess for SM8550: level 1 reads TYPE at both and reports which one is an LDO.
// Registers: 0x04 TYPE (0x04 LDO; 0x03, 0x1c, 0x21, 0x22 SMPS kinds), 0x05 SUBTYPE, 0x08 STATUS (bit 7 ready), 0x40/0x41 the set
// point in mV, 0x45 MODE, 0x46 EN_CTL (bit 7 enabled). Observer reads only (piano-wifi-spmi=1).
// What the chip needs (Project-SunUEFI patches/linux/7.3/0001-platform.patch, its WCN7861 votes): S5F 876-1000 mV, S4D 876-1036 mV,
// S7I 1312-1340 mV, S3G 1860-2000 mV; the stock RPMh minimums are lower (500 / 500 / 1224 mV), so level 2 votes the voltage too.
// order: the DT supply order, which is the order the rails are brought up in (level 2); 0 = never voted by this driver.
// minMv / maxMv: piano's own DT range of that regulator (regulator-min/max-microvolt of rsc@16500000 regulators-*), so the voted
// voltage is a fact of this board, not the 13T's: level 2 asks for minMv (what the chip needs) and never for more than maxMv.
struct Rail {
  const char *supply; const char *regulator; const char *cmdDb; uint8_t sid; uint8_t smps; uint8_t ldo; uint16_t millivolts;
  uint16_t minMv; uint16_t maxMv; uint8_t order; const char *shared;
};
constexpr Rail kRails[] = {   // smps / ldo: the regulator's number in its kind (0: not that kind)
  {"pmu vddio", "vreg_l3f_1p8", "ldof3", 5, 0, 3, 1800, 1800, 1800, 1, "BT vdd18-aon"},
  {"pmu vddio1p2", "vreg_l2f_1p2", "ldof2", 5, 0, 2, 1200, 1200, 1200, 2, "BT vdd12-io"},
  {"pmu vddaon", "vreg_s5f_0p88", "smpf5", 5, 5, 0, 880, 876, 1000, 3, "BT rfa0p75/aon"},
  {"pmu vdddig", "vreg_s4d_0p88", "smpd4", 3, 4, 0, 880, 876, 1036, 4, "BT vdd-dig"},
  {"pmu vddrfa1p2", "vreg_s7i_1p31", "smpi7", 8, 7, 0, 1310, 1312, 1340, 5, "BT rfa1p3 (on the 13T also the UFS vccq parent)"},
  {"pmu vddrfa1p8", "vreg_s3g_1p86", "smpg3", 6, 3, 0, 1860, 1864, 2000, 6, "BT rfa1p8"},
  {"phy vdda-phy", "vreg_l1f_0p88", "ldof1", 5, 0, 1, 880, 880, 920, 0, "always-on; UFS refgen, USB, CSI: never voted"},
  {"phy vdda-pll", "vreg_l3g_1p2", "ldog3", 6, 0, 3, 1200, 1200, 1256, 0, "the UFS PHY's and the DSI PHY's PLL: never voted, never lowered"},
};
constexpr unsigned kRailCount = sizeof kRails / sizeof kRails[0];
constexpr unsigned kVotedRails = 6;   // kRails[0..5]; the two PHY LDOs are read only (NativeUfs runs on one of them)
constexpr uint8_t smpsPage(unsigned n) { return uint8_t(0x9b + 3 * (n - 1)); }
constexpr uint8_t ldoPage(unsigned n) { return uint8_t(0xc0 + n); }
constexpr uint8_t ldoPageAlt(unsigned n) { return uint8_t(0x40 + n - 1); }
// Two PMIC GPIOs: BT_EN of the PMU (DT bt-enable-gpios <&pmic@5 gpio 3>; PM8550VE GPIO n at page 0x88 + n - 1, gpio@8800: SID 5 page
// 0x8a) and the 32 kHz sleep clock pin PAGANI and SHENG drive for the PMU (PMK8550 gpio3 "alt_sleep_clk", SID 0 page 0xba; piano's
// DT names no clock for wcn7860-pmu, mainline's MTP names RPMH_RF_CLK1). Registers 0x04 TYPE, 0x05 SUBTYPE, 0x08 STATUS (bit 0 the
// input level), 0x40 MODE_CTL, 0x41 DIG_VIN_CTL, 0x42 DIG_PULL_CTL, 0x44 DIG_OUT_SOURCE_CTL, 0x45 DIG_OUT_CTL, 0x46 EN_CTL.
struct PmicPin { const char *name; uint8_t sid; uint8_t page; };
constexpr PmicPin kPmicPins[] = {{"BT_EN (pm8550ve-f gpio3)", 5, 0x8a}, {"sleep clock (pmk8550 gpio3)", 0, 0xba}};
constexpr unsigned kPmicPinCount = sizeof kPmicPins / sizeof kPmicPins[0];
// SPMI arbiter v7 (DT spmi@c400000, qcom,ee = 0): the windows of SpmiObserver.h
// AOP command database (DT aop-cmd-db@81c60000, 0x20000 bytes, no-map): read only, copied out word by word (PianoKeyboard's way)
constexpr uint64_t kCmdDb = 0x81c60000, kCmdDbBytes = 0x20000;

// ================================================================================================= level 2: the rails by RPMh
// The application processor's RSC (DT rsc@16500000, qcom,drv-id 2): the HLOS's DRV is DRV-2 at 0x16520000, its TCS block at +0xd00,
// three ACTIVE TCSes first (qcom,tcs-config). The protocol and the register layout are PianoA830's Sm8750Rpmh.h / PianoPower's
// QcomRpmh.c (same repository): a VRM resource takes the set point in mV at +0, the enable at +4 and the mode at +8 (7 = NPM/HPM).
constexpr uint64_t kRscDrv2 = 0x16520000, kRscDrv2Bytes = 0x10000;
constexpr uint32_t kRscTcsBlock = 0xd00;
constexpr uint32_t kVrmVoltage = 0, kVrmEnable = 4, kVrmMode = 8, kVrmModeNpm = 7;
// pwrseq-qcom-wcn's wcn7850/peach entry (behaviour, not code): the rails in DT order, then WLAN_EN high and 50 ms before the chip
// answers. SHENG held WLAN_EN low 150 ms first so that an earlier start has stopped; PAGANI does the same.
constexpr unsigned kWlanEnLowMs = 150, kPmuPowerUpMs = 50;

// ================================================================================================= level 3: the root complex
// PARF, the SM8550 programming model (PCI = mainline pcie-qcom cfg_1_9_0; PAGANI has the same offsets from the 13T's vendor driver)
constexpr uint32_t kParfMhiClockResetCtrl = 0x174, kParfAxiMstrWrAddrHalt = 0x1a8, kParfIntAllClear = 0x228,
                   kParfIntAllMask = 0x22c, kParfDbiBaseHi = 0x354, kParfSlvSpaceHi = 0x35c, kParfAtuBaseHi = 0x638,
                   kParfBdfToSidTable = 0x2000;
constexpr uint32_t kParfDeviceTypeRc = 4, kParfPhyTestPwrDown = 1u << 0, kParfBdfToSidBypass = 1u << 0,
                   kParfSysCtrlMstrAxiClkEnable = 1u << 29, kParfMhiClockResetCtrlBypass = 1u << 4, kParfPmCtrlReqNotEntr = 1u << 5,
                   kParfAxiMstrWrHaltEnable = 1u << 31;
// The BDF-to-SID hash table: 256 words of (BDF << 16 | SID offset << 8 | next), indexed by a CRC-8 (polynomial 0x07, MSB first,
// the requester ID's high byte then its low byte) of the requester ID; used once the bypass bit is clear.
constexpr uint8_t kBdfHashPoly = 0x07;
constexpr uint16_t kRootRid = 0x0000, kEndpointRid = 0x0100;
// DBI: the type 1 header's memory window, and the PCI Express capability's link control 2 (capability + 0x30)
constexpr uint32_t kDbiMemBaseLimit = 0x20, kExpLinkCap = 0x0c, kExpLinkCtlSta = 0x10, kExpLinkCtl2 = 0x30;
constexpr uint32_t kCommandMemory = 1u << 1, kCommandMaster = 1u << 2;
// iATU, unrolled: control 1 (+0, the TLP type), control 2 (+4, bit 31 enable), base (+8/+0xc), limit (+0x10), target (+0x14/+0x18),
// upper limit (+0x20)
constexpr uint32_t kAtuCtrl1 = 0x00, kAtuCtrl2 = 0x04, kAtuBaseLo = 0x08, kAtuBaseHi = 0x0c, kAtuLimit = 0x10, kAtuTargetLo = 0x14,
                   kAtuTargetHi = 0x18, kAtuUpperLimit = 0x20;
constexpr uint32_t kAtuTypeMem = 0, kAtuTypeCfg0 = 4;
// The RCG sources: aux from the TCXO (CFG 0), rchng at 100 MHz (DT assigned-clock-rates 0x5f5e100; source 6 = GPLL0_OUT_EVEN with
// the divider field of 3, as mainline's and PAGANI's tables encode it); the pipe mux takes 0 = the PHY's pipe clock, 2 = TCXO.
constexpr uint32_t kAuxCfgTcxo = 0, kRchngCfg100MHz = (6u << 8) | 5u, kRcgUpdate = 1u << 0;
constexpr uint32_t kPipeMuxPhy = 0, kPipeMuxTcxo = 2, kTcsrClkRefEnable = 1u << 0;
// The GCC branch vote bits level 3 sets (the words are shared: PianoA830 votes GPLL0 in 0x52000, PianoTouch the QUP branches)
constexpr uint32_t kVote8Bits = 0x7f, kVote0Bits = (1u << 11) | (1u << 12) | (1u << 19) | (1u << 20) | (1u << 22);
// Link speeds: the PHY is gen3x2, but Gen3 needs cx/mx at NOM (DT opp-table: opp-level 0x100 for the two fastest OPPs), which
// nothing here votes, so the target link speed stays Gen2 unless piano-wifi-gen says otherwise (PAGANI's rule).
constexpr unsigned kMaxGen = 3, kDefaultGen = 2;
constexpr uint32_t kLinkTrainMs = 1000, kEndpointAnswerMs = 1000;

// ================================================================================================= level 4: MHI and firmware
// The endpoint's MHI registers live at the start of BAR0 (sheng, PAGANI; ath12k maps them the same way). BHI and BHIe are at the
// offsets the device reports in BHIOFF / BHIEOFF.
constexpr uint32_t kMhiRegLen = 0x00, kMhiBhiOff = 0x28, kMhiBhieOff = 0x2c, kMhiCtrl = 0x38, kMhiStatus = 0x48;
// The SoC reset request (bit 0): the MHI host writes it to force a device that supports a crash dump into its crash dump
// environment (the restart's test, piano-wifi-crashtest).
constexpr uint32_t kMhiSocResetReq = 0xb0, kMhiSocResetReqBit = 1u << 0;
constexpr uint32_t kMhiCfg = 0x10, kMhiErdbOff = 0x20, kMhiCcabap = 0x58, kMhiEcabap = 0x60, kMhiCrcbap = 0x68,
                   kMhiCtrlBase = 0x80, kMhiCtrlLimit = 0x88, kMhiDataBase = 0x98, kMhiDataLimit = 0xa0;
constexpr uint32_t kMhiCtrlReset = 1u << 1, kMhiStatusReady = 1u << 0, kMhiStatusSysErr = 1u << 2, kMhiStateShift = 8;
constexpr uint32_t kBhiImgAddrLo = 0x08, kBhiImgAddrHi = 0x0c, kBhiImgSize = 0x10, kBhiImgTxDb = 0x18, kBhiIntVec = 0x20,
                   kBhiExecEnv = 0x28, kBhiStatus = 0x2c, kBhiErrCode = 0x30;
// The rest of the BHI block (the MHI specification's names, as both MHI hosts use them): the version words at +0/+4, the three
// error debug words after the error code, the chip's serial number (+0x40: per unit, so a dump masks it) and the boot loader's
// anti-rollback version and segment count. The dumps read +0x00..+0x48 and nothing past it.
constexpr uint32_t kBhiVersionMinor = 0x00, kBhiVersionMajor = 0x04, kBhiErrDbg1 = 0x34, kBhiErrDbg2 = 0x38, kBhiErrDbg3 = 0x3c,
                   kBhiSerialNumber = 0x40, kBhiDumpBytes = 0x4c;
// What the boot loader reports about the chip after it read its fuses: six words of the MSM hardware ID from +0x4c and the 24 words
// of the OEM public key hash from +0x64 (the MHI specification's names; the host reads them before the boot). Never logged as
// values: level 4 logs how many are non-zero and a short digest, so two boots can be compared (an all-zero or changing hash would
// mean the boot loader could not read its fuses).
constexpr uint32_t kBhiMsmHwId = 0x4c, kBhiMsmHwIdWords = 6, kBhiOemPkHash = 0x64, kBhiOemPkHashWords = 24;
constexpr uint32_t kBhieTxVecAddrLo = 0x2c, kBhieTxVecAddrHi = 0x30, kBhieTxVecSize = 0x34, kBhieTxVecDb = 0x3c,
                   kBhieTxVecStatus = 0x44;
constexpr uint32_t kBhieDumpBytes = 0x7c;     // up to the receive vector's status (+0x78), which the crash dump path uses
constexpr uint32_t kMhiCoreDumpBytes = 0xa8;  // MHIREGLEN .. MHIDATALIMIT_HIGHER
constexpr uint32_t kMhiSeqMask = 0x3fffffffu, kMhiXferSuccess = 2, kMhiXferError = 3;
// The chip's register window in BAR0: offsets below 0x80000 are direct, higher ones go through the window register (PAGANI's choice
// for 0x110e, from the 13T's cnss2: 0x3278; WCN7850 and sheng use 0x310c). Level 4 reads only the SoC version through it.
constexpr uint32_t kChipWindowReg = 0x3278, kChipWindowEnable = 0x40000000, kChipWindowShift = 19, kChipWindowMask = 0x3f,
                   kChipWindowStart = 0x80000, kChipWindowRange = 0x7ffff;
constexpr uint32_t kChipTcsrSocHwVersion = 0x01b00000;
constexpr uint32_t kBar0BytesExpected = 0x200000;   // 2 MiB on WCN7850 (sheng); needs-boot for 0x110e
// The chip-side power-on reset this chip's own host runs at every power-up before MHI (Ubuntu's ath12k `pci.c`, sw_reset with
// power_on: behaviour; the offsets are facts of the chip, the same for every chip of the family it drives, WCN7860 included, and
// WifiPbl.h has the order): the chip's own PCIe PARF LTSSM word set to 0x111 (retried, as the link can be unsettled after a hot
// reset), the hot-reset bit of the chip's GCC (WCN7860 uses the QCC2072 register set: 0x1e65304; WCN7850's is 0x1e40304), the
// chip's PCIe interrupts cleared (a hot reset leaves one pending that the boot loader would take), the QFPROM power control's
// VDD4BLOW bit cleared (the fuse-blow supply off), the BHIe vector doorbells and status words cleared, the Q6 cookie read, the
// warm-boot entry word cleared and the reset cause read (it clears on read), the SoC's global reset pulsed (bit 0 of BAR0 +
// 0x3008, 10 ms each way; the window register is lost and written again), then MHICTRL's reset bit and 10 ms. Before 2026-11-12's
// fourth round only the last four ran, and only with piano-wifi-socreset=1; now the whole recipe is the default (docs §10.23).
constexpr uint32_t kChipSocGlobalReset = 0x3008, kChipSocGlobalResetBit = 1u << 0, kChipSocResetMs = 10;
constexpr uint32_t kChipPcieIntAllClear = 0x01e08228, kChipWlaonWarmSwEntry = 0x01f80504, kChipWlaonResetCause = 0x01f8060c;
constexpr uint32_t kChipParfLtssm = 0x01e081b0, kChipParfLtssmValue = 0x111, kChipGccHotReset = 0x01e65304,
                   kChipGccHotResetBit = 0x10, kChipQfpromPwrCtrl = 0x01f8031c, kChipQfpromVdd4Blow = 0x4,
                   kChipQ6Cookie = 0x01f80500, kChipLtssmTries = 5, kChipLtssmSettleMs = 5;
// The BHIe vector words ath12k clears by their BAR0 offsets (they are BHIEOFF 0x224 + 0x3c / 0x44 / 0x70 / 0x78 on this chip, which
// is also what the logs read: BHIEOFF 0x224), and the receive vector block the MHI host zeroes before the boot ("their power-on
// values are undefined": BHIe + 0x60 .. + 0x78, the address, size, doorbell and status of the crash dump's vector table).
constexpr uint32_t kChipTxVecDb = 0x360, kChipTxVecStatus = 0x368, kChipRxVecDb = 0x394, kChipRxVecStatus = 0x39c;
constexpr uint32_t kBhieRxVecAddrLo = 0x60, kBhieRxVecStatus = 0x78;
// The crash dump (RDDM) over the same receive block (the MHI specification's names, as the mainline host uses them; behaviour and
// offsets only): the vector table's address high at +0x64 (low at +0x60), its length in bytes at +0x68, the doorbell at +0x70
// (the session number in 29:0) and the status at +0x78 (29:0 the session the device answers, 31:30 its state: 2 complete, 3 an
// error). The host gives the table before the device's power-up, right after zeroing the block, so that a firmware that dies
// later can write its memory into the host's segments without asking; the host then only waits for the status. The size is the
// one this chip family's host reserves for it (0x420000 bytes, in 512 KiB segments: nine, the last one partly used), a fact of
// its MHI configuration.
constexpr uint32_t kBhieRxVecAddrHi = 0x64, kBhieRxVecSize = 0x68, kBhieRxVecDb = 0x70;
constexpr uint32_t kRddmBytes = 0x420000, kRddmSegBytes = 512 * 1024;
// The device wake doorbell: the last channel doorbell (channel 127, at CHDBOFF + 8 * 127), 1 while the host needs the device in M0,
// 0 when it lets it idle (M1, then the host's M2). The MHI host asserts it at every M0 transition and around each command or
// transfer; this polled host asserts it at mission mode and keeps it while its levels run (the device then never idles under it).
constexpr uint32_t kMhiDevWakeChannel = 127;

// ---- the PCIe NoC's bus clock manager (level 3, before the clocks) ----
// The endpoint's DMA leaves the controller through the PCIe aggregate NoC: Ubuntu's sm8750 interconnect driver has MASTER_PCIE_0
// (xm_pcie3) -> qns_pcie_mem_noc, whose bus clock manager is "SN4", not keep-alive, the only manager of that NoC; the gem NoC's
// SH0 and DDR's MC0 behind it are keep-alive. pcie-qcom votes this path ("pcie-mem") before it enables the controller's clocks
// and raises it to width x speed once the link is up; nothing votes it on native piano, and sheng (SM8550, hardware-verified)
// votes the same manager (SN7 there) at link-up, before its chip's first DMA. The vote is a BCM command: bit 30 commit, bit 29
// valid, the average in 27:14, the peak in 13:0, in the manager's units: peak kB/s x aux width / the node's bus width (8 bytes),
// x 1000 / aux unit (cmd-db's aux data: u32 unit, u16 width, u8 clock domain), a non-zero value never rounded to 0, at most 0x3fff.
constexpr const char *kNocBcmName = "SN4";
constexpr uint16_t kNocBusWidth = 8;
constexpr unsigned kPcieLanes = 2;
constexpr uint32_t kBcmCommit = 1u << 30, kBcmValid = 1u << 29, kBcmVoteMask = 0x3fff, kBcmVoteXShift = 14;
// pcie-qcom's peak per lane: the link's data rate after its encoding, in kB/s (Gen1 2000 Mb/s, Gen2 4000, Gen3 7876).
inline uint32_t pcieLaneKbps(unsigned gen) { return gen >= 3 ? 984500u : gen == 2 ? 500000u : 250000u; }
inline uint32_t bcmDiv(uint64_t num, uint64_t base)
{
  if (!base) return 0;
  if (num && num < base) return 1;   // a small vote is never lost
  const uint64_t q = num / base;
  return q > 0xffffffffu ? 0xffffffffu : uint32_t(q);
}
inline uint32_t bcmVote(uint64_t kbps, uint32_t unit, uint16_t width, uint16_t busWidth)
{
  if (!kbps || !unit || !width || !busWidth) return 0;
  const uint32_t v = bcmDiv(uint64_t(bcmDiv(kbps * width, busWidth)) * 1000u, unit);
  return v > kBcmVoteMask ? kBcmVoteMask : v;
}
inline uint32_t bcmCommand(uint32_t average, uint32_t peak)
{
  const uint32_t x = average > kBcmVoteMask ? kBcmVoteMask : average, y = peak > kBcmVoteMask ? kBcmVoteMask : peak;
  return kBcmCommit | ((x || y) ? kBcmValid : 0u) | x << kBcmVoteXShift | y;
}

// ---- the PCI status bits a DMA that failed leaves behind (type 0/1 headers, the PCI Express capability, AER) ----
// Status (the upper half of +0x04, and of +0x1c for the root port's secondary side): 27 signaled target abort, 28 received target
// abort, 29 received master abort (an Unsupported Request completion), 30 signaled system error, 31 detected parity error. Device
// status (+0x0a of the PCI Express capability): 0 correctable, 1 non-fatal, 2 fatal, 3 unsupported request detected. AER
// (extended capability 1): uncorrectable status at +0x04 (14 completion timeout, 15 completer abort, 16 unexpected completion,
// 20 unsupported request), correctable status at +0x10.
constexpr uint32_t kStatusErrorBits = 0xf8000000u, kExtCapStart = 0x100, kExtCapAer = 0x0001, kAerUncorrectable = 0x04,
                   kAerCorrectable = 0x10;
// The root port's type 1 windows besides the memory one (PCI-to-PCI bridge specification): I/O base/limit (the low half of +0x1c;
// the high half is the secondary status, write-one-to-clear) with its upper 16 bits at +0x30, and the prefetchable window at +0x24
// with its upper 32 bits at +0x28 / +0x2c. Linux's enumeration closes a window the bus does not need (base above limit: I/O 0xf0,
// prefetchable 0x0000fff0, uppers 0); level 3 does the same and logs what the controller had (2026-11-12, fourth round).
constexpr uint32_t kDbiIoBaseLimit = 0x1c, kDbiPrefBaseLimit = 0x24, kDbiPrefBaseHi = 0x28, kDbiPrefLimitHi = 0x2c,
                   kDbiIoUpper = 0x30;
constexpr uint32_t kIoWindowClosed = 0x000000f0u, kPrefWindowClosed = 0x0000fff0u, kIoUpperDisabled = 0x0000ffffu;
// The MSI capability (PCI): message control in the upper half of +0 (bit 0 enable, 3:1 vectors capable, 6:4 vectors enabled, 7
// 64-bit addresses, 8 per-vector masking), the address at +4 (+8 the high half when 64-bit), the data at +8 or +0xc, the mask at
// +0xc or +0x10. Command bit 10 disables INTx, as the host does when it enables MSI.
constexpr uint32_t kMsiCtlEnable = 1u << 0, kMsiCtlMmeMask = 7u << 4, kMsiCtl64 = 1u << 7, kMsiCtlMask = 1u << 8;
constexpr uint32_t kCommandIntxDisable = 1u << 10;
// The DesignWare controller's RAS DES event counters (a vendor-specific extended capability, ID 0x000b, whose header at +4 says
// ID 2, revision 4 on Qualcomm's controllers; Ubuntu's pcie-designware-debugfs.c is read for the facts only): the counter control
// at +8 (27:24 group, 23:16 event, 4:2 enable: 3 this event on, 0 no change; 7 the selected counter's status) and its data at +0xc.
// Group 7 counts TLPs by kind, group 3 errors. Level 4 enables the ones below on both ends of the link before the doorbell and
// logs how far each moved: whether the chip asked for the image at all, and what the root port answered.
constexpr uint32_t kExtCapVendor = 0x000b, kRasDesVsecId = 2, kRasDesVsecRev = 4, kRasDesCtrl = 0x08, kRasDesData = 0x0c;
constexpr uint32_t kRasDesEnableOn = 3u << 2, kRasDesStatus = 1u << 7;
struct RasEvent { const char *name; uint8_t group, event; };
constexpr RasEvent kRasEvents[] = {
  {"tx MRd", 7, 0x01}, {"tx MWr", 7, 0x00}, {"tx CplD", 7, 0x07}, {"tx Cpl", 7, 0x06},
  {"rx MRd", 7, 0x0c}, {"rx MWr", 7, 0x0b}, {"rx CplD", 7, 0x12}, {"rx Cpl", 7, 0x11},
  {"UR", 3, 0x03},     {"CA", 3, 0x04},     {"CTO", 3, 0x05},
};
constexpr unsigned kRasEventCount = sizeof kRasEvents / sizeof kRasEvents[0];
// The firmware file (never in this repository): the stock modem_a FAT, image/peach/amss20.bin = ath12k's amss.bin, 6930496 bytes.
// BHI carries its first 512 KiB (the secondary boot loader); BHIe carries the second ELF that follows when the bytes at 512 KiB are
// "\177ELF" (peach), else the whole file (WCN7850). Segments of 512 KiB, as the 13T's cnss2 cuts them.
constexpr const char *const kFirmwarePartitions[] = {"modem_a", "modem_b"};
constexpr const char *const kFirmwareDirs[] = {"image/peach", "image"};
constexpr const char *kAmssName = "amss20.bin";
constexpr uint32_t kMhiSblBytes = 512 * 1024, kMhiSegBytes = 512 * 1024, kMhiMaxSegments = 32;
// The identity of the stock file Ubuntu runs (xiaomipad-8pro-mainline firmware/piano-wlan.json, stock build OS3.0.303.0.WPYCNXM:
// ath12k/WCN7860/hw2.0/amss.bin = image/peach/amss20.bin, 6930496 bytes), and of its first 512 KiB, the image BHI carries (the
// boot loader: a signed 32-bit ARM ELF of 0x2e630 bytes, zero to 512 KiB; then the Hexagon ELF to the end of the file). Hashes
// only: level 4 compares what is in the DMA window, read back the way the chip reads it, with these (docs §10.23).
constexpr uint32_t kAmssStockBytes = 6930496;
constexpr uint8_t kAmssStockSha256[32] = {
  0x02, 0xbb, 0xc0, 0x28, 0xf7, 0x32, 0x29, 0xc9, 0x6c, 0xce, 0xde, 0x74, 0x74, 0xb2, 0x30, 0xd3,
  0x9d, 0x21, 0x86, 0xdc, 0x5d, 0x9d, 0xb7, 0x73, 0x7f, 0x69, 0x38, 0x1b, 0x8d, 0xd3, 0x3c, 0xac};
constexpr uint8_t kAmssStockSblSha256[32] = {
  0xc0, 0xe4, 0xbb, 0x91, 0x7b, 0x29, 0x79, 0xf5, 0x77, 0x90, 0x92, 0x28, 0x60, 0xaa, 0x01, 0xa5,
  0x2c, 0xa7, 0x77, 0x2d, 0xb6, 0x2e, 0x0f, 0x95, 0x97, 0xe0, 0xbd, 0x56, 0xff, 0x79, 0xd7, 0x08};
constexpr uint32_t kDmaWindowBytes = 24u << 20;   // the boot loader, the segments, the vector table and the MHI contexts

// ======================================================== level 5: the MHI channels, QRTR, and the WLAN firmware's QMI service
// The MHI register block's remaining offsets (the MHI specification's names, as both the mainline host and the vendor host use
// them; behaviour only, nothing copied): the channel doorbell array's offset, the command ring doorbell, and the element sizes.
// A doorbell is a 64-bit value written as two words, the high half first.
constexpr uint32_t kMhiChdbOff = 0x18, kMhiCrdbLo = 0x70, kMhiCrdbHi = 0x74;
// A ring element (TRE) is 16 bytes: a 64-bit pointer and two words. The words' fields:
//   transfer:  word0 = length (15:0); word1 = type 2 (23:16) | bei (10) | ieot (9) | ieob (8) | chain (0)
//   command:   word1 = channel (31:24) | command (23:16); start channel = 18, stop = 17, reset = 16
//   event:     word0 = code (31:24) | length (15:0) — for a state change or an execution environment event the new value is in
//              31:24 instead; word1 = channel (31:24) | type (23:16); transfer completion 0x22, command completion 0x21,
//              state change 0x20, execution environment change 0x40. Completion codes: 1 success, 2 end of transfer, 3 the
//              buffer overflowed, 4 end of block, 5 out of buffers, 6 the channel went back to doorbell mode, 0x10 undefined
//              error, 0x11 a bad element.
//   An event's pointer: a command completion's is the command element's bus address on the command ring; a TRANSFER
//   completion's is the bus address of the transfer ring ELEMENT it completes — never the buffer that element names. The host
//   finds its buffer through the element (the MHI host keeps a buffer record per element and walks its own read pointer up to
//   the one the event names). An event with code 5 or 6 completes nothing: the host rings that channel's doorbell again if it
//   has elements the chip has not taken.
constexpr uint32_t kTreTypeTransfer = 2, kTreCmdStart = 18, kTreCmdStop = 17, kTreCmdReset = 16;
constexpr uint32_t kEvTypeTransfer = 0x22, kEvTypeCmdCompletion = 0x21, kEvTypeStateChange = 0x20, kEvTypeEeChange = 0x40;
constexpr uint32_t kEvCodeSuccess = 1, kEvCodeEot = 2, kEvCodeOverflow = 3, kEvCodeEob = 4, kEvCodeOob = 5, kEvCodeDbMode = 6;
constexpr uint32_t kEvCodeUndefined = 0x10, kEvCodeBadTre = 0x11;
constexpr uint32_t kTreIeot = 1u << 9, kTreIeob = 1u << 8, kTreChain = 1u << 0, kTreBei = 1u << 10;
// A channel context's words: configuration (channel state 7:0, burst mode 9:8, poll configuration 15:10), type (1 outbound to the
// device, 2 inbound), the event ring it reports on; then base, length, read and write pointers (64-bit each).
constexpr uint32_t kChanCfg = 0, kChanType = 4, kChanErIndex = 8, kChanRBase = 12, kChanRLen = 20, kChanRp = 28, kChanWp = 36;
constexpr uint32_t kChanStateDisabled = 0, kChanStateEnabled = 1, kChanStateRunning = 2;
constexpr uint32_t kChanBurstDisable = 2;   // in the burst mode field (9:8)
constexpr uint32_t kChanTypeOutbound = 1, kChanTypeInbound = 2;
// The two IPC router channels of this chip family, and how the vendor's own host sizes them: channel 20 carries packets to the
// device, 21 carries them back, 64 elements each, both reporting on the second event ring (the 256-element one level 4 already
// programs), burst mode disabled, and a receive buffer of 8 KiB per element (facts of the chip's MHI configuration).
constexpr uint32_t kChanIpcrOut = 20, kChanIpcrIn = 21;
constexpr uint32_t kIpcrElements = 64, kIpcrBufferBytes = 8 * 1024;
constexpr uint32_t kIpcrEventRing = 1;      // the data ring of WifiMhi.h's two
constexpr uint32_t kIpcrOutBuffers = 4;     // ours: at most one QMI request is in flight, three spare
// The command ring level 4 already programs has 8 elements; level 5 uses it for the two "start channel" commands.
constexpr uint32_t kMhiCommandTimeoutMs = 2000;

// QRTR on this link: our node number and the port our client binds. The router's control port is 0xfffffffe (WifiQrtr.h). The
// firmware's node number is whatever its hello says; the service's port comes from its announcement.
constexpr uint32_t kQrtrLocalNode = 1, kQrtrClientPort = 0x4000;   // the first port of the router's ephemeral range
// The WLAN firmware's QMI service: id 69, version 1, instance 1 on this chip family (the announcement's instance word is
// version | instance << 8). The service's messages level 5 uses:
constexpr uint32_t kWlfwService = 0x45, kWlfwVersion = 1, kWlfwInstance = 1;
constexpr uint32_t kWlfwInstanceWord = kWlfwVersion | kWlfwInstance << 8;
enum WlfwMessage : uint16_t {
  kWlfwIndRegister = 0x0020, kWlfwWlanMode = 0x0022, kWlfwWlanCfg = 0x0023, kWlfwCap = 0x0024, kWlfwBdfDownload = 0x0025,
  kWlfwWlanIni = 0x002f, kWlfwHostCap = 0x0034, kWlfwRequestMemInd = 0x0035, kWlfwRespondMem = 0x0036,
  kWlfwFwMemReadyInd = 0x0037, kWlfwFwReadyInd = 0x0038, kWlfwM3Info = 0x003c, kWlfwQdssDownload = 0x0044,
  kWlfwPhyCap = 0x0057, kWlfwAuxUcInfo = 0x005a,
};
// The client identifier the host announces when it registers for indications, and the largest data payload one download message
// carries (both facts of the service).
constexpr uint32_t kWlfwClientId = 0x4b4e454c, kWlfwMaxDataBytes = 6144;
// The host capability bits this platform must set: the host handles its own C-states, the chip uses its internal sleep clock
// (piano's DT names no clock for the PMU, open question 3 in wifi.md), and the platform can reset the PCIe link globally.
constexpr uint8_t kHostCapCstate = 0x04, kHostCapInternalSleepClock = 0x02, kHostCapPcieGlobalReset = 0x08;
constexpr uint8_t kHostCapNmModem = kHostCapCstate | kHostCapInternalSleepClock | kHostCapPcieGlobalReset;
// The firmware feature list this chip's entry asks for: "the host does not pull PERST# on reset" and "the auxiliary microcode is
// supported" (bits 4 and 6 of the service's feature enumeration). The QDSS configuration miss bit is *not* set for this chip,
// which is why the QDSS configuration is one of the downloads below.
constexpr uint64_t kWlfwFeaturePerstNoPull = 1ull << 4, kWlfwFeatureAuxUc = 1ull << 6;
constexpr uint64_t kWlfwFeatureList = kWlfwFeaturePerstNoPull | kWlfwFeatureAuxUc;
constexpr uint32_t kWlfwMemCfgModeDefault = 0;   // the memory configuration mode: the full-size one
// The firmware's memory region types, and the download types.
enum WlfwMemType : uint32_t {
  kMemHostDdr = 0x1, kMemBdf = 0x2, kMemM3Dump = 0x3, kMemCaldb = 0x4, kMemMloGlobal = 0x8, kMemPageable = 0x9,
  kMemLpassShared = 0xb,
};
enum WlfwBdfType : uint8_t { kBdfTypeBin = 0, kBdfTypeElf = 1, kBdfTypeRegdb = 4, kBdfTypeCalibration = 5 };
constexpr uint32_t kWlfwMaxMemSegments = 52, kWlfwMaxMemCfg = 2;
constexpr uint32_t kWlfwChunkLimit = 2u << 20;   // a single region larger than this is answered with the "ask again smaller" form
constexpr uint32_t kBoardFileLimit = 256 * 1024; // this chip's board-file size cap
constexpr uint8_t kBoardIdDefault = 0xff;        // the file identifier when the firmware reports no board identifier
constexpr uint32_t kFirmwareModeNormal = 0, kFirmwareModeOff = 4;
constexpr const char *kHostVersionString = "WIN";   // the host version string the service expects
constexpr uint32_t kWlfwTimeoutMs = 10000;          // the service's own request timeout
// The firmware files level 5 reads from the same stock partition level 4 reads (never from this repository): the board file is the
// China-region one of this unit's stock image, and the names are the stock ones (ath12k's own names in wifi.md section 2).
constexpr const char *kBoardName = "bd_p81.elf";          // board data, an ELF: download type 1
constexpr const char *kRegdbName = "regdb_xiaomi.bin";    // the regulatory database: download type 4
constexpr const char *kM3Name = "phy_ucode20.elf";        // the PHY microcode, handed over by address
constexpr const char *kAuxUcName = "aux_ucode20.elf";     // the auxiliary microcode, handed over by address
constexpr const char *kQdssName = "qdss_trace_config_v2.cfg";   // the trace configuration, downloaded in segments

// The copy engine configuration level 5 sends the firmware (the chip's own pipes, which the data path of level 6 then uses).
// pipe direction: 1 into the host, 2 out of the host, 3 both ways, 4 host to host.
enum CePipeDir : uint32_t { kCeDirNone = 0, kCeDirIn = 1, kCeDirOut = 2, kCeDirInOut = 3, kCeDirHostToHost = 4 };
constexpr uint32_t kCeFlagsDefault = 0, kCeFlagNoInterrupt = 8;
struct CePipeConfig { uint32_t pipe, dir, entries, bytesMax, flags; };
// This chip family's nine pipes: 0 control out, 1 control/data in, 2 the firmware's messages in, 3 the host's messages out,
// 4 the host's data out, 5 packet log in, 6 the firmware's own copies, 7 host to host, 8 reserved for the data accelerator.
constexpr CePipeConfig kCePipes[] = {
  {0, kCeDirOut, 32, 2048, kCeFlagsDefault},
  {1, kCeDirIn, 32, 2048, kCeFlagsDefault},
  {2, kCeDirIn, 32, 2048, kCeFlagsDefault},
  {3, kCeDirOut, 32, 2048, kCeFlagsDefault},
  {4, kCeDirOut, 256, 256, kCeFlagsDefault | kCeFlagNoInterrupt},
  {5, kCeDirIn, 32, 2048, kCeFlagsDefault},
  {6, kCeDirInOut, 32, 16384, kCeFlagsDefault},
  {7, kCeDirHostToHost, 0, 0, kCeFlagsDefault | kCeFlagNoInterrupt},
  {8, kCeDirInOut, 32, 16384, kCeFlagsDefault},
};
constexpr unsigned kCePipeCount = sizeof kCePipes / sizeof kCePipes[0];
// The host transport's services and the pipes they use. A service identifier is group << 8 | index: group 0 reserved (control),
// 1 the firmware's message interface, 3 the host's data messages.
struct CeServiceConfig { uint32_t service, dir, pipe; };
constexpr uint32_t kSvcCtrl = 0x0001, kSvcWmiControl = 0x0100, kSvcWmiDataBe = 0x0101, kSvcWmiDataBk = 0x0102,
                   kSvcWmiDataVi = 0x0103, kSvcWmiDataVo = 0x0104, kSvcHttData = 0x0300;
constexpr CeServiceConfig kCeServices[] = {
  {kSvcWmiDataVo, kCeDirOut, 3}, {kSvcWmiDataVo, kCeDirIn, 2},
  {kSvcWmiDataBk, kCeDirOut, 3}, {kSvcWmiDataBk, kCeDirIn, 2},
  {kSvcWmiDataBe, kCeDirOut, 3}, {kSvcWmiDataBe, kCeDirIn, 2},
  {kSvcWmiDataVi, kCeDirOut, 3}, {kSvcWmiDataVi, kCeDirIn, 2},
  {kSvcWmiControl, kCeDirOut, 3}, {kSvcWmiControl, kCeDirIn, 2},
  {kSvcCtrl, kCeDirOut, 0}, {kSvcCtrl, kCeDirIn, 2},
  {kSvcHttData, kCeDirOut, 4}, {kSvcHttData, kCeDirIn, 1},
};
constexpr unsigned kCeServiceCount = sizeof kCeServices / sizeof kCeServices[0];
// The shadow registers: a list of register offsets inside BAR0 that stand in for a ring's head or tail pointer, so that the host
// writes one 32-bit word instead of a descriptor pointer. The chip carries 40 of them from BAR0 + 0x8fc, four bytes apart, and the
// firmware learns which ring each stands for from the order of this list (the offsets of the rings' own head pointers; a
// destination ring's tail pointer is its head pointer's offset plus four). The rings exist only at level 6, so level 5 sends the
// list only with piano-wifi-shadow=1 and the builder is a host-tested function (WifiWlfw.h shadowList).
constexpr uint32_t kShadowBase = 0x8fc, kShadowRegisters = 40, kShadowMax = 60;
constexpr uint32_t kShadowHpToTp = 4;
// The ring head-pointer offsets of this chip's register map (its unit's own base plus the ring's offset in it), in the order the
// list is built: the non-copy-engine rings first, then the copy engines' source, destination and destination-status rings.
constexpr uint32_t kUnitReo = 0x00a38000, kUnitTcl = 0x00a44000, kUnitWbm = 0x00a34000;
constexpr uint32_t kUnitCe0Src = 0x01b80000, kUnitCe0Dst = 0x01b81000, kUnitCe1Src = 0x01b82000, kUnitCe1Dst = 0x01b83000;
constexpr uint32_t kReo1RingHp = 0x3048, kReo2RingHp = 0x3050, kReoSw0RingHp = 0x3088, kReoCmdHp = 0x3020, kSw2ReoHp = 0x3028,
                   kReoStatusHp = 0x30a8;
constexpr uint32_t kTcl1RingHp = 0x2000, kTcl2RingHp = 0x2008, kTclRingHp = 0x2028, kTclStatusHp = 0x2048;
constexpr uint32_t kWbmIdleLinkHp = 0x30b8, kWbmSwReleaseHp = 0x3010, kWbm0ReleaseHp = 0x30c8, kWbm1ReleaseHp = 0x30d0;
constexpr uint32_t kCeDstRingHp = 0x400, kCeDstStatusRingHp = 0x408;

// Level 5's own sizes: the IPC router's buffers, the firmware's memory regions and the QMI message buffer all come out of the same
// arena as level 4's image, so the window is larger when level 5 runs (piano-wifi-dma, default 24 MiB at level 4, 64 at level 5).
constexpr uint32_t kDmaWindowBytesL5 = 64u << 20;
// The 32-bit question (wifi.md section 10.11): the chip's own driver gives it 36-bit addresses for the firmware's regions but
// 32-bit ones for the rings of the data path, and XNU's memory is all above 4 GiB on piano, so a bypassing stream (level 3's) can
// never produce a 32-bit address. piano-wifi-iova=1 therefore gives stream 0x1401 a translating context bank whose window starts
// here and maps the arena in 2 MiB blocks (WifiSmmuWindow.h); the addresses handed to the chip are then this window's.
constexpr uint32_t kIovaWindowBase = 0x20000000;   // 512 MiB: inside the first 1 GiB of a 32-bit input space
constexpr uint32_t kIovaBlockBytes = 2u << 20;

// ================================================== level 6: the copy engine, the host transport and the firmware's messages
// Facts of the chip and of the three protocols on top of it, read from the Ubuntu kernel of section 3 for the wire shapes only
// (`ce.c`, `hal*.c`, `htc.[ch]`, `wmi.[ch]`, `hw.c`, `core.c`); no code, comment or table of it is here. wifi.md section 14 has
// the message table.
//
// ---- the copy engine's rings (the chip's register map, through the BAR0 window of level 4) ----
// Three rings per pipe, each a contiguous array of 32-bit descriptors in the DMA window:
//   the source ring (host writes a buffer to send, the chip reads it),
//   the destination ring (host writes an empty buffer, the chip fills it) — also a *source*-direction ring: the host produces,
//   the destination-status ring (the chip writes one entry per filled buffer, with its length) — a destination-direction ring.
// Each ring has two pointers. The host's own pointer lives in the chip's register space (the R2 group below); the chip's lives in
// host memory, at an address the host programs into the ring (so no register has to be read to poll).
// Both pointers of every ring count 32-bit words (so does the size field of its base register), not bytes and not descriptors.
constexpr uint32_t kCeUnitStride = 0x2000;        // between pipe n's and pipe n+1's source (and destination) unit
constexpr uint32_t kCeStatusRingBase = 0x58;      // the destination-status ring's register block, in the destination unit
constexpr uint32_t kCeR2Hp = 0x400, kCeR2Tp = 0x404;             // the host's pointer, in the unit's register block
constexpr uint32_t kCeStatusR2Hp = 0x408, kCeStatusR2Tp = 0x40c;  // the destination-status ring's, in the destination unit
constexpr uint32_t kCeDstRingCtrl = 0xb0;         // in the destination unit: the largest buffer the chip may fill (bits 15:0)
constexpr uint32_t kCeDstRingCtrlMaxLen = 0xffffu;
// The register block of one ring (R0): base address low at +0, then these offsets. A source-direction ring (the source ring and
// the destination ring) and a destination-direction ring (the destination-status ring) differ in two of them, which is why both
// sets are here: they are the deltas of this chip's transmit-command and reorder ring blocks.
constexpr uint32_t kRingBaseMsb = 0x04, kRingId = 0x08, kRingMisc = 0x10;
constexpr uint32_t kSrcRingTpAddrLo = 0x1c, kSrcRingTpAddrHi = 0x20, kSrcRingConsumerInt0 = 0x30, kSrcRingConsumerInt1 = 0x34;
constexpr uint32_t kDstRingHpAddrLo = 0x14, kDstRingHpAddrHi = 0x18, kDstRingProducerInt = 0x24;
// base_msb: the address's high bits (7:0) and the ring's size in 32-bit words (27:8). id: the ring's identifier (15:8) and the
// descriptor's size in words (7:0). misc: bit 6 enables the ring, bit 1 switches the loop count off (source rings).
constexpr uint32_t kRingBaseMsbAddrHi = 0xffu, kRingBaseMsbSizeShift = 8, kRingBaseMsbSizeMask = 0xfffffu;
constexpr uint32_t kCeRingSizeMaxWords = 0xffffu;   // what a copy-engine ring's size field takes, narrower than the field
constexpr uint32_t kRingIdEntrySizeMask = 0xffu, kRingIdRingIdShift = 8;
constexpr uint32_t kRingMiscEnable = 1u << 6, kRingMiscLoopCountDisable = 1u << 1;
constexpr uint32_t kRingAddrLowMask = 0xffffffffu, kRingAddrHiShift = 32;
// The ring identifiers this chip gives its copy-engine rings (a destination-direction ring carries its own in its register).
constexpr uint32_t kRingIdCe0Src = 64, kRingIdCe0Dst = 81, kRingIdCe0DstStatus = 100;
// A source descriptor is four words, a destination descriptor two, a destination-status descriptor four.
constexpr uint32_t kCeSrcDescWords = 4, kCeDstDescWords = 2, kCeStatusDescWords = 4;
// source: word0 address low, word1 address high (7:0) | byte swap (9) | gather (11) | length (31:16), word2 an identifier the
// status entry carries back (15:0), word3 the ring identifier (27:20) and the loop count (31:28).
constexpr uint32_t kCeDescAddrHiMask = 0xffu, kCeDescLenShift = 16, kCeDescLenMask = 0xffffu;
constexpr uint32_t kCeDescGather = 1u << 11, kCeDescByteSwap = 1u << 9;
constexpr uint32_t kCeDescMetaMask = 0xffffu, kCeDescRingIdShift = 20;
// status: word0 length (31:16) and the same flags, word3 the identifier (15:0) the source descriptor carried.
constexpr uint32_t kCeStatusLenShift = 16, kCeStatusLenMask = 0xffffu;
// The host's own ring sizes (ours, not the firmware's: the two sides of a pipe are sized independently; the firmware's are the
// nine entries of kCePipes, which level 5 sends). Only the four pipes the host transport uses are created: 0 and 3 out, 1 and 2
// in. Every ring is a power of two, as the chip's index arithmetic needs.
struct CeHostPipe { uint8_t pipe; uint32_t srcEntries, dstEntries, bufferBytes; };
constexpr CeHostPipe kCeHostPipes[] = {
  {0, 16, 0, 0},        // the transport's control messages out
  {1, 0, 32, 2048},     // the firmware's data messages in (its data interface's answers, P23)
  {2, 0, 64, 2048},     // the firmware's and the transport's messages in
  {3, 32, 0, 0},        // the host's messages out
  {4, 32, 0, 0},        // the host's data-interface messages out (P23: only when the receive buffers are asked for)
};
constexpr unsigned kCeHostPipeCount = sizeof kCeHostPipes / sizeof kCeHostPipes[0];
constexpr unsigned kCePipeCtrlOut = 0, kCePipeDataIn = 1, kCePipeMsgIn = 2, kCePipeMsgOut = 3, kCePipeHttOut = 4;
// The pipes a level plans and programs, by pipe number: level 6's four, and pipe 4 as well with the receive buffers (P23), so
// that a boot without them programs exactly the registers it always did.
constexpr uint32_t kCePipeMaskLevel6 = 0x0fu, kCePipeMaskWithHtt = 0x1fu;
constexpr uint32_t kCeSendBuffers = 8;            // ours: the messages in flight on the two outbound pipes
constexpr uint32_t kCeSendBufferBytes = 2048;     // the largest message either outbound pipe carries
constexpr uint32_t kCeDstKeepFree = 2;            // elements of a destination ring left without a buffer

// ---- the host transport (HTC) ----
// Every message carries an 8-byte header: word0 endpoint (7:0) | flags (15:8) | payload length (31:16); word1 trailer length
// (7:0) | sequence (15:8). The control endpoint is 0; the firmware answers on the pipe the service's entry names.
constexpr uint32_t kHtcHeaderBytes = 8;
constexpr uint32_t kHtcHdrEndpointMask = 0xffu, kHtcHdrFlagsShift = 8, kHtcHdrLengthShift = 16;
constexpr uint32_t kHtcFlagNeedCreditUpdate = 0x01, kHtcFlagTrailerPresent = 0x02;
constexpr uint32_t kHtcCtrlTrailerShift = 0, kHtcCtrlSequenceShift = 8;
enum HtcMessage : uint16_t {
  kHtcMsgReady = 1, kHtcMsgConnectService = 2, kHtcMsgConnectServiceResp = 3, kHtcMsgSetupComplete = 4,
  kHtcMsgSetupCompleteEx = 5, kHtcMsgSuspendComplete = 6, kHtcMsgNackSuspend = 7, kHtcMsgWakeFromSuspend = 8,
};
// The ready message: word0 message id (15:0) | credit count (31:16); word1 credit size (15:0) | endpoints (23:16). The extended
// form adds word2: version (7:0) | messages per bundle (15:8).
// The connect request: word0 message id (15:0) | service (31:16); word1 connection flags (15:0) | metadata length (23:16).
// Its answer: word0 message id (15:0) | service (31:16); word1 status (7:0) | endpoint (15:8) | largest message (31:16).
constexpr uint32_t kHtcReadyCreditCountShift = 16, kHtcReadyCreditSizeMask = 0xffffu, kHtcReadyEndpointsShift = 16;
constexpr uint32_t kHtcMsgIdMask = 0xffffu, kHtcServiceShift = 16;
constexpr uint32_t kHtcConnFlagsMask = 0xffffu, kHtcConnRecvAllocShift = 8;
constexpr uint32_t kHtcConnFlagDisableCreditFlow = 1u << 3;
constexpr uint32_t kHtcRespStatusMask = 0xffu, kHtcRespEndpointShift = 8, kHtcRespMaxMessageShift = 16;
constexpr uint32_t kHtcConnStatusSuccess = 0;
// The trailer's records: an identifier, a length, two padding bytes, then the records themselves; a credit report is one
// endpoint and one credit count per four bytes.
constexpr uint32_t kHtcRecordCredits = 1, kHtcRecordHeaderBytes = 4, kHtcCreditReportBytes = 4;
// Nine endpoints, 0 to 8: the firmware may hand out the last one, and a credit report may name it.
constexpr unsigned kHtcEndpoints = 9, kHtcMaxControlMessage = 256, kHtcMaxMessage = 4096;

// ---- the firmware's own message interface (WMI) ----
// A command is a 4-byte header (the command identifier in bits 23:0) and then TLVs; an event is TLVs alone. A TLV's header is one
// 32-bit word: length (15:0) and tag (31:16), and its value is padded to a whole number of words.
constexpr uint32_t kWmiCmdHeaderBytes = 4, kWmiTlvHeaderBytes = 4;
constexpr uint32_t kWmiCmdIdMask = 0xffffffu;
constexpr uint32_t kWmiTlvLenMask = 0xffffu, kWmiTlvTagShift = 16;
enum WmiCommand : uint32_t {
  kWmiCmdInit = 0x00001, kWmiCmdStartScan = 0x03001, kWmiCmdStopScan = 0x03002, kWmiCmdScanChanList = 0x03003,
  kWmiCmdPdevSetParam = 0x04003, kWmiCmdPdevSetHwMode = 0x0401e, kWmiCmdVdevCreate = 0x05001, kWmiCmdVdevDelete = 0x05002,
};
enum WmiEvent : uint32_t {
  kWmiEvtServiceReady = 0x00001, kWmiEvtReady = 0x00002, kWmiEvtServiceAvailable = 0x00003, kWmiEvtScan = 0x03001,
  kWmiEvtChanInfo = 0x04002, kWmiEvtServiceReadyExt = 0x04009, kWmiEvtPdevSetHwModeResp = 0x04010,
  kWmiEvtServiceReadyExt2 = 0x04022, kWmiEvtVdevDeleteResp = 0x05006, kWmiEvtMgmtRx = 0x07001, kWmiEvtDebugMessage = 0x1d003,
  kWmiEvtDiag = 0x1d011, kWmiEvtRegChanListCc = 0x3a001, kWmiEvtRegChanListCcExt = 0x3a003,
};
enum WmiTag : uint32_t {
  kWmiTagArrayUint32 = 0x010, kWmiTagArrayByte = 0x011, kWmiTagArrayStruct = 0x012, kWmiTagArrayFixedStruct = 0x013,
  kWmiTagServiceReadyEvent = 0x020, kWmiTagHalRegCapabilities = 0x021, kWmiTagHostMemRequest = 0x022, kWmiTagReadyEvent = 0x023,
  kWmiTagScanEvent = 0x024, kWmiTagMgmtRxHeader = 0x02c, kWmiTagInitCmd = 0x04a, kWmiTagResourceConfig = 0x04b,
  kWmiTagHostMemoryChunk = 0x04c, kWmiTagStartScanCmd = 0x04d, kWmiTagStopScanCmd = 0x04e, kWmiTagChannel = 0x050,
  kWmiTagPdevSetParamCmd = 0x052, kWmiTagVdevCreateCmd = 0x056, kWmiTagVdevDeleteCmd = 0x057,
  kWmiTagVdevTxrxStreams = 0x19b, kWmiTagServiceReadyExtEvent = 0x1ac, kWmiTagVdevDeleteRespEvent = 0x1c2,
  kWmiTagPdevSetHwModeCmd = 0x203, kWmiTagPdevSetHwModeResp = 0x206, kWmiTagServiceAvailableEvent = 0x22f,
  kWmiTagPdevBandToMac = 0x24b,
  kWmiTagServiceReadyExt2Event = 0x334,
};
// The resource configuration this chip's firmware wants (its own entry's values; the structure is 72 words after the TLV header,
// and a firmware of another version may read more of them, which is why the whole structure is written and the words this driver
// does not set are left zero).
constexpr uint32_t kWmiResourceConfigWords = 72;
constexpr uint32_t kWmiCfgNumVdevs = 4, kWmiCfgNumPeers = 16, kWmiCfgNumTids = 32, kWmiCfgNumOffloadPeers = 3,
                   kWmiCfgNumOffloadReorderBuffs = 3, kWmiCfgNumPeerKeys = 2, kWmiCfgAstSkidLimit = 16,
                   kWmiCfgRxTimeoutLoPri = 100, kWmiCfgRxTimeoutHiPri = 40, kWmiCfgDecapModeNativeWifi = 1,
                   kWmiCfgScanMaxPending = 4, kWmiCfgBmissOffloadMaxVdev = 3, kWmiCfgRoamOffloadMaxVdev = 3,
                   kWmiCfgRoamOffloadMaxApProfiles = 8, kWmiCfgTxDbgLogSize = 1024, kWmiCfgVowConfig = 0,
                   kWmiCfgGtkOffloadMaxVdev = 2, kWmiCfgNumMsduDesc = 0x400, kWmiCfgMaxFragEntries = 0xa,
                   kWmiCfgNumTdlsVdevs = 1, kWmiCfgNumTdlsConnTableEntries = 8, kWmiCfgBeaconTxOffloadMaxVdev = 2,
                   kWmiCfgNumMulticastFilterEntries = 0x20, kWmiCfgNumWowFilters = 0x16, kWmiCfgRxBatchmode = 1,
                   kWmiCfgPeerMapUnmapVersion = 1, kWmiCfgUsePdevId = 1;
// The two flag words of that structure, as this firmware's own host always sends them: the 64-bit channel-information form and
// the acknowledgement signal strength in flag1; "work out the next beacon count" and "no address-table indications" in flags2.
constexpr uint32_t kWmiCfgFlag1 = (1u << 5) | (1u << 18);
constexpr uint32_t kWmiCfgFlags2 = (1u << 9) | (1u << 18);
constexpr uint32_t kWmiMaxMemRequests = 32;       // how many the firmware may ask for in its service-ready event
constexpr uint32_t kWmiPdevIdSoc = 0;
// A station virtual device, and the scan this level runs on it.
constexpr uint32_t kWmiVdevTypeStation = 2, kWmiVdevSubtypeNone = 0;
constexpr uint32_t kWmiBandCount = 2;             // the stream entries a virtual device carries: 2.4 GHz and 5 GHz
constexpr uint32_t kWmiVdevStatsIdInvalid = 0xff;
constexpr uint32_t kWmiStartScanWords = 39;       // the start-scan structure's words after its TLV header
constexpr uint32_t kWmiStopScanOne = 0;           // stop the scan of this identifier (and not every scan of the radio)
constexpr uint32_t kWmiScanId = 0xa000, kWmiScanRequestorId = 1;
// The priority field: this firmware's own host sets it in its own structure and never writes it into the command, so the
// firmware reads a zero there, and so does this driver (the same wire bytes).
constexpr uint32_t kWmiScanPriorityZero = 0;
constexpr uint32_t kWmiScanFlagPassive = 0x1, kWmiScanFlagChanStatEvent = 0x10, kWmiScanFlagFilterProbeReq = 0x20;
constexpr uint32_t kWmiScanDwellActiveMs = 50, kWmiScanDwellPassiveMs = 150, kWmiScanMinRestMs = 50,
                   kWmiScanMaxRestMs = 500, kWmiScanProbeDelayMs = 5, kWmiScanMaxTimeMs = 20000;
// The per-band dwell times of the same structure's last words: none for the 2.4 GHz band (it takes the general one) and
// 70 ms for the 6 GHz band's two, which this scan never reaches.
constexpr uint32_t kWmiScanDwellActive2GhzMs = 0, kWmiScanDwell6GhzMs = 70;
enum WmiScanEventType : uint32_t {
  kWmiScanEvStarted = 1u << 0, kWmiScanEvCompleted = 1u << 1, kWmiScanEvBssChannel = 1u << 2,
  kWmiScanEvForeignChannel = 1u << 3, kWmiScanEvDequeued = 1u << 4, kWmiScanEvPreempted = 1u << 5,
  kWmiScanEvStartFailed = 1u << 6, kWmiScanEvRestarted = 1u << 7, kWmiScanEvForeignChannelExit = 1u << 8,
};
enum WmiScanReason : uint32_t {
  kWmiScanReasonCompleted = 0, kWmiScanReasonCancelled = 1, kWmiScanReasonPreempted = 2, kWmiScanReasonTimedOut = 3,
  kWmiScanReasonInternalFailure = 4,
};
// The channels a passive scan of this level visits: the 2.4 GHz band's 13 channels and the 5 GHz band's non-radar ones, as
// centre frequencies in MHz (the firmware's regulatory domain decides which it really visits, and its regulatory event says so).
constexpr uint32_t kScanChannels24[] = {2412, 2417, 2422, 2427, 2432, 2437, 2442, 2447, 2452, 2457, 2462, 2467, 2472};
constexpr uint32_t kScanChannels5[] = {5180, 5200, 5220, 5240, 5745, 5765, 5785, 5805, 5825};
constexpr unsigned kScanChannelCount24 = sizeof kScanChannels24 / sizeof kScanChannels24[0];
constexpr unsigned kScanChannelCount5 = sizeof kScanChannels5 / sizeof kScanChannels5[0];
constexpr unsigned kScanChannelMax = kScanChannelCount24 + kScanChannelCount5;
constexpr unsigned kScanEntriesMax = 32;          // how many networks one scan keeps (the rest are counted, not kept)
constexpr unsigned kSsidMax = 32;                 // 802.11: a service set identifier is at most 32 bytes
// A management frame's status word: a frame with one of these bits set is thrown away, as this firmware's own host does (a
// frame that failed its check may carry any bytes at all, and a network's address must never come from one).
constexpr uint32_t kWmiRxStatusErrCrc = 0x01, kWmiRxStatusErrDecrypt = 0x08, kWmiRxStatusErrMic = 0x10,
                   kWmiRxStatusErrKeyCacheMiss = 0x20;
constexpr uint32_t kWmiRxStatusBad = kWmiRxStatusErrCrc | kWmiRxStatusErrDecrypt | kWmiRxStatusErrKeyCacheMiss;
// The signal strength of a received management frame is the signal-to-noise ratio the firmware reports plus the noise floor,
// which is what its own host uses when it has measured none of its own.
constexpr int32_t kNoiseFloorDbm = -95;
// 802.11 management frames the scan delivers: the frame control's type and subtype, and where the addresses are.
constexpr uint32_t kDot11FcTypeMask = 0x0c, kDot11FcSubtypeMask = 0xf0, kDot11FcTypeManagement = 0x00;
constexpr uint32_t kDot11SubtypeProbeResponse = 0x50, kDot11SubtypeBeacon = 0x80;
constexpr uint32_t kDot11HeaderBytes = 24, kDot11BeaconFixedBytes = 12;   // timestamp, interval, capability
constexpr uint32_t kDot11ElementSsid = 0, kDot11ElementDsParams = 3;
constexpr uint32_t kWmiTimeoutMs = 10000;         // the deadline of each level 6 step (the firmware's own is five seconds)
constexpr uint32_t kScanWaitMsDefault = 12000;    // how long the scan itself may take before the level gives up on it

// ---- what the firmware wants before a virtual device and a scan (P22, docs §10.27) ----
// On a single-radio chip of this family the host sends, after the firmware's ready event and before it creates anything: the
// hardware mode (WMI_PDEV_SET_HW_MODE, "two bands at once"), four radio parameters, the chain masks, and the channel list its
// regulatory event allows (WMI_SCAN_CHAN_LIST). Its virtual device is never created with an all-zero address either: a host
// that has none of its own makes a locally administered one. Facts of the same Ubuntu tree (§3), behaviour only.
constexpr uint32_t kWmiHwModeDbs = 1;             // the mode a single-radio chip of this family is put in
constexpr uint32_t kWmiPdevParamTxChainMask = 0x01, kWmiPdevParamRxChainMask = 0x02, kWmiPdevParamDynamicBw = 0x0a,
                   kWmiPdevParamPmfQos = 0x22, kWmiPdevParamArpAcOverride = 0x23, kWmiPdevParamMeshMcastEnable = 0x8f;
// The address a virtual device takes when the firmware reports none: locally administered (bit 1 of the first byte), not a
// group address, and piano's own three middle bytes so that two tablets on one network cannot collide by construction. The
// unit's own address is in the persist partition and is never built into an image (docs §13.1). The last byte is 0x04:
// 0x01 is PianoNullEthernet's built-in en0, 0x02 and 0x03 the two ends of PianoDwc3's USB network. Boot 10h: with 0x01 the
// station's interface carried en0's address, macOS never gave it a name of its own (it was never attached to the network
// stack), and ifconfig's "en0" was PianoNullEthernet all along.
constexpr uint8_t kLocalMac[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x04};
// The bits of piano-wifi-l6pre: which of those pieces level 6 does before it creates its virtual device, so that one boot can
// take Ubuntu's whole order and the next can leave a piece out without a rebuild.
constexpr uint32_t kPreHwMode = 1u << 0, kPrePdevParams = 1u << 1, kPreChanList = 1u << 2, kPreVdevMac = 1u << 3,
                   kPreRegWait = 1u << 4, kPrePace = 1u << 5, kPreNoScan = 1u << 6;
// P23 (docs §10.28): bit 7 the receive buffers — the data interface connected, its version, the receive rings with their
// buffers, and a **second scan** after them, so one boot compares a scan without them with one with them; bit 8 the scan's
// diagnostics (the channel-information counters and the radio's statistics after each scan); bit 9 the receive buffers
// return to "software ring 1", as the chip's own host has them, instead of to the firmware's own manager.
constexpr uint32_t kPreRxRings = 1u << 7, kPreDiag = 1u << 8, kPreRbmSw1 = 1u << 9;
constexpr uint32_t kPreDefault = kPreHwMode | kPrePdevParams | kPreChanList | kPreVdevMac | kPreRegWait | kPrePace |
                                 kPreRxRings | kPreDiag;
constexpr uint32_t kPreRegWaitMsDefault = 2000;   // for the firmware's regulatory event, which it sends after the init
constexpr uint32_t kPrePaceMsDefault = 50;        // between the pieces, so that a log names the last command before a death
constexpr uint32_t kPreHoldMsDefault = 8000;      // with kPreNoScan: how long the level holds after the virtual device

// ---- the receive buffers and the scan's diagnostics (P23, docs §10.28) ----
// On this chip family the receive DMA has no buffers of its own: the host fills a ring of empty buffers for the firmware
// (host to firmware, "software to software"), and the firmware hands them on to one buffer ring per radio, which the host
// also provides (empty). No frame — not even a beacon the firmware would forward as a management-frame event — can be received
// before that. The rings are announced through the firmware's data interface (HTT, transport service 0x0300 on pipes 4 out /
// 1 in, connected before the message interface, no credit flow control and no receive credits), with a version request after
// the firmware's ready event. Facts of the Ubuntu tree of §3 (dp_htt, dp_rx, hal): behaviour, message layouts and values only.
constexpr uint32_t kHttMsgVersionReq = 0x00, kHttMsgSrngSetup = 0x0b, kHttMsgRxRingSelectionCfg = 0x0c;
constexpr uint32_t kHttT2hVersionConf = 0x00, kHttT2hPeerMap = 0x03;
constexpr uint32_t kHttVersionMajor = 3;          // the major version this host speaks
// The version request: word 0 the message type (7:0); word 1 one option — tag (7:0) 5 "TCL metadata version", length (15:8) 4,
// value (31:16) 2. Its answer: word 0 type (7:0), minor (15:8), major (23:16).
constexpr uint32_t kHttOptionTclMetadataVersion = 5, kHttOptionTclMetadataLength = 4, kHttTclMetadataV2 = 2;
// A ring set up (HTT_SRING_SETUP, 13 words): word 0 type (7:0), the radio (15:8: the radio's number plus one for a ring of the
// receive DMA, the radio itself for a host-to-firmware ring), the ring (23:16), its kind (31:24); 1-2 its base; 3 its size in
// words (15:0), an entry's size in words (23:16) and "no loop count" (bit 25, rings the host produces into the hardware); 4-5
// where the head pointer lives, 6-7 the tail pointer (both in host memory: these rings belong to the radio's own units); 8-10
// the MSI address and data (none); 11 interrupt batching (none); 12 low threshold and "answer wanted" (none).
constexpr uint32_t kHttSrngSetupWords = 13;
constexpr uint32_t kHttSrngLoopCountDisable = 1u << 25;
enum HttRingKind : uint32_t { kHttHwToSw = 0, kHttSwToHw = 1, kHttSwToSw = 2 };
enum HttRingId : uint32_t {
  kHttRingRxdmaHostBuf = 0, kHttRingRxdmaMonitorStatus = 1, kHttRingHost1ToFwRxbuf = 5, kHttRingRxdmaNonMonitorDest = 7,
};
// A receive-buffer entry: word 0 the buffer's address (31:0); word 1 its high bits (7:0), the manager it returns to (11:8) and
// a cookie of the host's (31:12). The returning manager this chip's host gives its receive buffers is "software ring 1" (6);
// "the firmware's own" is 4, which keeps a buffer the firmware has finished with inside the chip (the host's release rings are
// level 8's). The destination ring of the receive DMA's errors has entries of 8 words.
constexpr uint32_t kRxBufEntryWords = 2, kRxDmaDstEntryWords = 8;
constexpr uint32_t kRxBufRbmFw = 4, kRxBufRbmSw1 = 6;
constexpr uint32_t kRxBufAddrHiMask = 0xffu, kRxBufRbmShift = 8, kRxBufCookieShift = 12, kRxBufCookieMask = 0xfffffu;
// How many of each this host makes (the chip's own host uses 2048/4096/1024; the firmware takes the sizes from the messages).
constexpr uint32_t kRxRefillEntries = 512, kRxMacBufEntries = 512, kRxErrDstEntries = 128, kRxMonStatusEntries = 64;
constexpr uint32_t kRxBufferBytes = 2048, kRxRadios = 2;
// The scan's diagnostics: the firmware's channel-information event (one at the start and one at the end of every channel visit:
// its counters of busy and receiving cycles and its noise floor say whether the radio hears anything at all), and its radio
// statistics (WMI_REQUEST_STATS for the radio, answered by WMI_UPDATE_STATS: the receive counters say whether frames reached
// the firmware). Channel information: error (0), frequency (1), start 0 / end 1 (2), noise floor (3), busy cycles (4), all
// cycles (5), two power words (6, 7), receiving cycles (8), our network's (9), 11b data time (10), transmitting cycles (11),
// the counters' clock in MHz (12), the device (13).
constexpr uint32_t kWmiEvtUpdateStats = 0x1d004;
constexpr uint32_t kWmiCmdRequestStats = 0x16001;
constexpr uint32_t kWmiTagChanInfoEvent = 0x026, kWmiTagRequestStatsCmd = 0x08f, kWmiTagStatsEvent = 0x046;
constexpr uint32_t kWmiStatsPdev = 1u << 2, kWmiStatsVdev = 1u << 3;
// A device record (level 8, boot 10q), 41 words: the device, the beacons' and the data's SNR, frames sent per access category
// (4), frames received, retries per category (4), failures per category (4), RTS failures and successes, receive errors,
// receive discards, frames not acknowledged, the last ten transmit rates and the last ten beacon RSSIs.
constexpr uint32_t kWmiVdevStatsWords = 41;
// The stats event: its fixed structure (stats kind, then how many radio, device, peer, beacon-filter, channel, MIB records,
// the radio, beacon and two extended peer counts) and a byte array of records. A radio record is 44 words: 7 of its own (noise
// floor, transmitting, receiving, busy and all cycles, PHY errors, power), 23 of transmission, 14 of reception (mid-PPDU route
// changes, statuses received, four fragment counters, MSDUs and MPDUs through the data interface, MSDUs and MPDUs delivered
// to the firmware itself, oversize A-MSDUs, PHY errors, PHY errors dropped, MPDU errors).
constexpr uint32_t kWmiStatsEventWords = 11, kWmiPdevStatsWords = 44, kWmiPdevStatsRxAt = 30;

// ---- level 7: the regulatory event, the channel list, a started station, a peer, the association (WifiSta.h, WifiAssoc.h) ----
// Wire facts of the same Ubuntu tree (docs/drivers/wifi.md section 3): the identifiers count up from their group's first
// command or event (the group in bits 23:12, the first of a group is 1), the tags are positions in the firmware's tag list. No
// code, comment or table of that tree is here.
enum WmiStaCommand : uint32_t {
  kWmiCmdVdevStart = 0x05003, kWmiCmdVdevUp = 0x05005, kWmiCmdVdevStop = 0x05006, kWmiCmdVdevDown = 0x05007,
  kWmiCmdVdevSetParam = 0x05008, kWmiCmdVdevInstallKey = 0x05009, kWmiCmdPeerCreate = 0x06001, kWmiCmdPeerDelete = 0x06002,
  kWmiCmdPeerSetParam = 0x06004, kWmiCmdPeerAssoc = 0x06005, kWmiCmdMgmtTxSend = 0x07008, kWmiCmdStaPowersaveMode = 0x09001,
};
enum WmiStaEvent : uint32_t {
  kWmiEvtVdevStartResp = 0x05001, kWmiEvtVdevStopped = 0x05002, kWmiEvtVdevInstallKeyComplete = 0x05003,
  kWmiEvtPeerStaKickout = 0x06001, kWmiEvtPeerAssocConf = 0x06006, kWmiEvtPeerDeleteResp = 0x06007,
  kWmiEvtMgmtTxCompletion = 0x07006,
};
enum WmiStaTag : uint32_t {
  kWmiTagVdevStartRespEvent = 0x028, kWmiTagVdevStoppedEvent = 0x029, kWmiTagPeerStaKickoutEvent = 0x02b,
  kWmiTagScanChanListCmd = 0x04f, kWmiTagVdevStartCmd = 0x058, kWmiTagVdevUpCmd = 0x05c, kWmiTagVdevStopCmd = 0x05d,
  kWmiTagVdevInstallKeyCompleteEvent = 0x02a, kWmiTagVdevDownCmd = 0x05e, kWmiTagVdevSetParamCmd = 0x05f,
  kWmiTagVdevInstallKeyCmd = 0x060, kWmiTagPeerCreateCmd = 0x061, kWmiTagPeerDeleteCmd = 0x062,
  kWmiTagPeerSetParamCmd = 0x064, kWmiTagPeerAssocCmd = 0x065, kWmiTagVhtRateSet = 0x066, kWmiTagStaPowersaveModeCmd = 0x06c,
  kWmiTagMgmtTxSendCmd = 0x1a6, kWmiTagMgmtTxComplEvent = 0x1a7, kWmiTagPeerAssocConfEvent = 0x1b2,
  kWmiTagPeerDeleteRespEvent = 0x1c3, kWmiTagRegRule = 0x260, kWmiTagRegChanListCcEvent = 0x261, kWmiTagRegRuleExt = 0x3a9,
  kWmiTagRegChanListCcExtEvent = 0x3aa, kWmiTagMloPeerCreateParams = 0x3d5,
};
// The regulatory event (both forms begin with the same fourteen words: status, radio, country (two characters in the low half),
// radios, country number, domain, radar region, radio bitmap, the two bands' least and largest bandwidths, the two bands' rule
// counts); the extended form follows them with its 6 GHz words. Then one array of rules: the 2.4 GHz band's first, then the
// 5 GHz band's (then the 6 GHz band's, which this driver reads past). A rule is its header and three words (four in the
// extended form): start (15:0) and end (31:16) frequency; largest bandwidth (15:0), power in dBm (23:16) and antenna gain
// (31:24); its flags (15:0).
constexpr uint32_t kRegEventWords = 14, kRegExtEventWords = 78;
constexpr uint32_t kRegRuleWords = 3, kRegRuleExtWords = 4;
constexpr uint32_t kRegRuleFlagDisabled = 1u << 0, kRegRuleFlagNoIr = 1u << 1, kRegRuleFlagRadar = 1u << 3,
                   kRegRuleFlagNoOfdm = 1u << 6, kRegRuleFlagIndoorOnly = 1u << 9;
constexpr unsigned kRegRulesMax = 16;             // per band; a country has a handful
// The channel list (WMI_SCAN_CHAN_LIST): the fixed structure (channel count, flags, radio), then an array of channel
// structures, each its header and six words: frequency, the two centre frequencies, the information word, and two of
// regulatory power. The information word: the radio mode (5:0), passive (7), radar (10), HT (11), VHT (12), HE (17). The first
// power word carries the least (7:0), largest (15:8) and regulatory (23:16) power and the class (31:24); the second the antenna
// gain (7:0) and the largest transmit power (15:8). The channel list's powers are in half dBm, a started device's in dBm.
constexpr uint32_t kWmiChannelWords = 6;
constexpr uint32_t kWmiChanInfoModeMask = 0x3f, kWmiChanInfoPassive = 1u << 7, kWmiChanInfoDfs = 1u << 10,
                   kWmiChanInfoAllowHt = 1u << 11, kWmiChanInfoAllowVht = 1u << 12, kWmiChanInfoAllowHe = 1u << 17;
constexpr uint32_t kWmiChanListAppend = 1u << 0;
constexpr unsigned kWmiChanListMax = 58;          // channels per command, as this firmware's own host sends them
// Radio modes of the channel and the peer: legacy only at this level (no HT, VHT or HE element goes out in the association).
constexpr uint32_t kWmiModeLegacy5 = 0, kWmiModeLegacy24 = 1, kWmiModeLegacy24Cck = 2;
// HT and VHT (level 7's piano-wifi-phy, boot 10r; 10q's legacy association capped TCP at about 24 Mbit/s, the 54 Mbit/s
// rate's): the firmware's modes for them (its list counts on from the legacy ones), its peer flags, the rate-control
// capabilities of a peer, the channel's HT40-above bit, and 802.11's elements and fields.
constexpr uint32_t kWmiModeHt20 = 4, kWmiModeHt20G = 5, kWmiModeHt40 = 6, kWmiModeHt40G = 7, kWmiModeVht20 = 8,
                   kWmiModeVht40 = 9, kWmiModeVht80 = 10;
constexpr uint32_t kWmiPeerFlagHt = 0x1000, kWmiPeerFlag40 = 0x2000, kWmiPeerFlagStbc = 0x8000, kWmiPeerFlagLdpc = 0x10000,
                   kWmiPeerFlagDynMimoPs = 0x20000, kWmiPeerFlagStaticMimoPs = 0x40000, kWmiPeerFlagSpatialMux = 0x200000,
                   kWmiPeerFlagVht = 0x02000000, kWmiPeerFlag80 = 0x04000000;
constexpr uint32_t kWmiRcDs = 0x01, kWmiRcCw40 = 0x02, kWmiRcSgi = 0x04, kWmiRcHt = 0x08, kWmiRcTxStbc = 0x20,
                   kWmiRcRxStbcShift = 6, kWmiRcTs = 0x200;
constexpr uint32_t kWmiChanInfoHt40Plus = 1u << 6;
constexpr uint32_t kDot11ElementVhtCap = 191, kDot11ElementVhtOperation = 192;
constexpr uint32_t kDot11HtCapBytes = 26, kDot11VhtCapBytes = 12;
constexpr uint16_t kDot11HtCapLdpc = 0x0001, kDot11HtCap40 = 0x0002, kDot11HtCapSmPsMask = 0x000c, kDot11HtCapSmPsDisabled = 0x000c,
                   kDot11HtCapSmPsStatic = 0x0000, kDot11HtCapSmPsDynamic = 0x0004, kDot11HtCapSgi20 = 0x0020,
                   kDot11HtCapSgi40 = 0x0040, kDot11HtCapTxStbc = 0x0080, kDot11HtCapRxStbcMask = 0x0300;
constexpr uint32_t kDot11HtCapRxStbcShift = 8;
constexpr uint32_t kDot11VhtCapRxLdpc = 0x10, kDot11VhtCapSgi80 = 0x20, kDot11VhtCapTxStbc = 0x80, kDot11VhtCapRxStbc1 = 0x100,
                   kDot11VhtCapAmpduShift = 23, kDot11VhtCapAmpduMask = 7u << 23;
// The channels level 7 may put in that list, as centre frequencies: the 2.4 GHz band's 13 and the 5 GHz band's 25 (36-64,
// 100-144, 149-165); the regulatory event's rules decide which go out and which are passive or radar channels.
constexpr uint32_t kAssocChannels24[] = {2412, 2417, 2422, 2427, 2432, 2437, 2442, 2447, 2452, 2457, 2462, 2467, 2472};
constexpr uint32_t kAssocChannels5[] = {5180, 5200, 5220, 5240, 5260, 5280, 5300, 5320, 5500, 5520, 5540, 5560, 5580,
                                        5600, 5620, 5640, 5660, 5680, 5700, 5720, 5745, 5765, 5785, 5805, 5825};
constexpr unsigned kAssocChannelCount = sizeof kAssocChannels24 / sizeof kAssocChannels24[0] +
                                        sizeof kAssocChannels5 / sizeof kAssocChannels5[0];
// A started station (WMI_VDEV_START_REQUEST): the fixed structure is 28 words after its header — the device (0), requestor
// (1), beacon interval (2), DTIM period (3), flags (4: LDPC receive bit 3, hidden network bit 0, protected management frames
// bit 1), the name's length and 32 bytes (5-13; a station sends none), beacon rate and power, notice-of-absence count,
// hardware acknowledgement off (14-17), the preferred transmit and receive streams (18, 19), HE operation (20), radar wait
// (21), domain (22), least data rate (23), multiple-network flags (24: bit 0 "not a multiple-network AP") and device (25), EHT
// operation (26) and the puncturing bitmap (27), which this firmware's own host sends as the complement of its own (all
// ones for an unpunctured channel). Then the channel structure on its own (its own header), then an empty array of
// notice-of-absence descriptors.
constexpr uint32_t kWmiVdevStartWords = 28;
constexpr uint32_t kWmiVdevStartLdpcRx = 1u << 3, kWmiVdevStartPmf = 1u << 1;
constexpr uint32_t kWmiMbssidNonMbssidAp = 1u << 0;
constexpr uint32_t kWmiVdevStartOk = 0;
// The station up (WMI_VDEV_UP): device (0), association identifier (1), the network's address (2-3), the transmitting
// network's address (4-5) and two multiple-network words (6, 7), the last four zero for a plain network. Stop and down: the
// device alone. The start's answer (WMI_VDEV_START_RESP) is twelve words: the device (0), the requestor (1), what it answers
// (2: 0 a start, 1 a restart), the status (3: 0 taken), the chain mask (4) and the stream mode (5).
constexpr uint32_t kWmiVdevUpWords = 8, kWmiVdevStartRespWords = 6;
// A device parameter (WMI_VDEV_SET_PARAM): device, parameter, value. The one this level sets is the stream count.
constexpr uint32_t kWmiVdevParamNss = 0x22;
// The station's power save (WMI_STA_POWERSAVE_MODE): device, mode (0 off). Off at this level: the radio stays awake.
constexpr uint32_t kWmiStaPsOff = 0, kWmiStaPsOn = 1;
// A peer (WMI_PEER_CREATE): device, the peer's address (two words), its type (0 default); then an array holding one
// multi-link parameter structure (its header and a flags word, zero: not a multi-link peer), which this firmware's own host
// always sends. Delete: device and address. A peer parameter (WMI_PEER_SET_PARAM): device, address, parameter, value.
constexpr uint32_t kWmiPeerTypeDefault = 0;
constexpr uint32_t kWmiPeerParamAuthorize = 3;
// The peer's association (WMI_PEER_ASSOC): the fixed structure is 61 words after its header — the address (0-1), device (2), a
// new association (3), the association identifier (4), the flags (5), the capability (6), the listen interval (7), HT
// capability, largest A-MPDU and its density (8-10), the rate capability (11), streams (12), VHT capability (13), the radio
// mode (14), two HT information words (15, 16), the legacy and HT rate counts (17, 18), a bandwidth/stream override (19), a
// 10-word HE threshold block (20-29), HE words (30-39), the station type (40), BSS idle (41), authentication mode (42), extended
// flags (43), puncturing (44), EHT words (45-50) and a second 10-word threshold block (51-60). Then the legacy rates as
// bytes, the HT rates as bytes, the VHT rate set structure on its own (five words: the receive side's largest rate and its
// set, the transmit side's two, and a stream/rate word; all zero for a legacy peer),
// and four arrays of structures (HE rate sets, multi-link parameters, EHT rate sets, multi-link partners), all empty here.
constexpr uint32_t kWmiPeerAssocWords = 61, kWmiVhtRateSetWords = 5;
// The keys (WMI_VDEV_INSTALL_KEY): the fixed structure is 25 words after its header — the device (0), the peer's address
// (1-2), the key's index (3), its kind (4: 0 pairwise, 1 group), the cipher (5: 0 none, 2 TKIP, 4 CCMP, 7 CMAC), the receive
// sequence counter as 64 bits (6-7), the group one (8-9) and the transmit one (10-11), two 16-byte WAPI counters (12-19), the
// key's length (20), the two TKIP microcode lengths (21, 22), and whether a group-key identifier follows and that identifier
// (23, 24). Then the key itself as a byte array, padded to a whole word (its real length is word 20).
constexpr uint32_t kWmiInstallKeyWords = 25;
constexpr uint32_t kWmiKeyPairwise = 0, kWmiKeyGroup = 1;
constexpr uint32_t kWmiCipherNone = 0, kWmiCipherTkip = 2, kWmiCipherCcmp = 4, kWmiCipherCmac = 7;
constexpr uint32_t kWmiTkipMicBytes = 8;   // each Michael key of a TKIP key (transmit, then receive)
constexpr uint32_t kWmiPeerFlagAuth = 0x1, kWmiPeerFlagQos = 0x2, kWmiPeerFlagNeedPtk4Way = 0x4, kWmiPeerFlagNeedGtk2Way = 0x10,
                   kWmiPeerFlagPmf = 0x08000000;
constexpr uint32_t kWmiRateCck = 0x80;            // a legacy rate byte: 500 kb/s units, bit 7 for the CCK rates
constexpr uint32_t kAssocListenInterval = 5;      // beacons, as this firmware's own host and its 802.11 layer send it
// A management frame out (WMI_MGMT_TX_SEND): device, a descriptor number of the host's (it comes back in the completion), the
// frequency (0: the device's own channel), the frame's bus address (low, high), the frame's length, how many of its bytes are
// copied into the command too, and "transmit parameters valid" (0). Then those first bytes (at most 64) as a byte array. The
// firmware reads the whole frame from the bus address: it must be in the 32-bit window.
constexpr uint32_t kWmiMgmtTxWords = 8, kWmiMgmtTxInlineMax = 64;
constexpr uint32_t kWmiMgmtTxStatusOk = 0;        // the completion's status: 0 acknowledged, anything else not
// 802.11 frames of the association (the frame control's first byte, type management, and the fields each body begins with).
constexpr uint8_t kDot11AssocRequest = 0x00, kDot11AssocResponse = 0x10, kDot11Disassoc = 0xa0, kDot11Auth = 0xb0,
                  kDot11Deauth = 0xc0;
constexpr uint32_t kDot11AuthOpen = 0, kDot11AuthBodyBytes = 6, kDot11AssocRespFixedBytes = 6;
constexpr uint16_t kDot11CapEss = 0x0001, kDot11CapPrivacy = 0x0010, kDot11CapShortPreamble = 0x0020,
                   kDot11CapShortSlot = 0x0400;
constexpr uint32_t kDot11ElementRates = 1, kDot11ElementTim = 5, kDot11ElementRsn = 48, kDot11ElementExtRates = 50;
constexpr uint16_t kDot11ReasonLeaving = 3;
// RSN suites: the 00-0F-AC organisation; ciphers 2 TKIP, 4 CCMP; key management 2 PSK, 6 PSK with SHA-256, 8 SAE. RSN
// capability bits 6 (management frame protection required) and 7 (capable).
constexpr uint32_t kRsnOui = 0x000fac;
constexpr uint8_t kRsnCipherTkip = 2, kRsnCipherCcmp = 4, kRsnAkmPsk = 2, kRsnAkmPskSha256 = 6, kRsnAkmSae = 8;
constexpr uint16_t kRsnCapMfpRequired = 1u << 6, kRsnCapMfpCapable = 1u << 7;
// How long level 7 waits, by default (piano-wifi-assoc's bits change none of them).
constexpr uint32_t kAssocProfileWaitMs = 600000;  // for the join profile (machdep.piano_wifi_join), after level 6's scan
constexpr uint32_t kAssocFrameWaitMs = 500, kAssocFrameTries = 3;   // an authentication or association answer, and retries
constexpr uint32_t kAssocHoldMs = 30000;          // associated: how long the level watches the link before its teardown
constexpr uint32_t kAssocScanDwellMs = 300;       // the targeted scan's passive dwell on the network's channel
constexpr uint32_t kBgScanId = 0xa020;             // level 7's background scan after a fast restart (published)
constexpr uint32_t kAssocScanId = 0xa010;          // level 7's own scans: clear of level 6's 0xa000 and 0xa002
constexpr uint32_t kAssocFrameBuffers = 4, kAssocFrameBytes = 1024;

// ---- level 7, the join as this chip's own host runs it (WifiSta.h; docs/drivers/wifi.md §13.3) ----
// Facts of the Ubuntu tree of §3 (mac.c, peer.c, dp.c, dp_rx.c, wifi7/hal_rx.c, wifi7/hal_desc.h, wmi.[ch], dp_htt.[ch]):
// identifiers, tags, field places and bit positions, read for those facts only; no code, comment or table of it is here.
// This chip family starts a station's virtual device only once its peer exists ("vdev_start_delay"): the order is the peer, the
// firmware's data interface naming it (HTT peer map), the peer's data set-up (its default routing, then one receive reorder
// queue per traffic identifier, 0-16), the virtual device started on the network's channel, Open System authentication and the
// association request as management frames of the message interface, the peer's association, the station up; the keys and the
// authorisation come after the four-way handshake (piece 3, user space).
// The station's parameters this chip's host sends right after its virtual device is created: the transmit encapsulation and
// the receive decapsulation (2 = 802.3: en1 is an Ethernet interface), the stream count, three power-save parameters (wake on
// receive, wake on every transmit, no PS-Poll limit) and power save off.
constexpr uint32_t kWmiVdevParamTxEncapType = 0x30, kWmiVdevParamRxDecapType = 0x5b;
constexpr uint32_t kWmiTxRxRaw = 0, kWmiTxRxNativeWifi = 1, kWmiTxRxEthernet = 2;
constexpr uint32_t kWmiCmdStaPowersaveParam = 0x09002, kWmiTagStaPowersaveParamCmd = 0x06d;
constexpr uint32_t kWmiStaPsParamRxWakePolicy = 0, kWmiStaPsParamTxWakeThreshold = 1, kWmiStaPsParamPspollCount = 2;
// level 8's power save (boot 10q): the time without traffic after which the station dozes (milliseconds)
constexpr uint32_t kWmiStaPsParamInactivityTime = 3;
constexpr uint32_t kWmiStaPsRxWakePolicyWake = 0, kWmiStaPsTxWakeThresholdAlways = 1, kWmiStaPsPspollCountNoMax = 0;
// The radio's transmit power limits (WMI_PDEV_SET_PARAM 3 and 4, 2.4 and 5 GHz), which this chip's host sends right after a
// virtual device: the value in half-dB (7:0) and a reason (15:8). For WCN7860 that host sends its platform limit, 30 (15 dBm),
// with the SAR reason 1 (the value the vendor host sends at every start).
constexpr uint32_t kWmiPdevParamTxPowerLimit2g = 0x03, kWmiPdevParamTxPowerLimit5g = 0x04;
constexpr uint32_t kWmiTxPowerLimitValue = 30u | 1u << 8;
// The peer's data set-up: WMI_PEER_SET_PARAM "default routing" = hash steering on (bit 0) and the receive ring the peer's
// frames go to in 3:1 (the ring's number counts from 1: radio 0's ring is 1); then WMI_PEER_REORDER_QUEUE_SETUP for each
// traffic identifier 0-16 (16 is the non-QoS one): the device, the peer's address, the identifier, the queue descriptor's bus
// address (low, high), the queue number (the identifier again), "window size valid" and the window size (1: no block ack yet).
constexpr uint32_t kWmiPeerParamDefaultRouting = 19;
constexpr uint32_t kDpRxHashEnable = 1, kDpReoDestRing = 1;
constexpr uint32_t kWmiCmdPeerReorderQueueSetup = 0x06013, kWmiTagReorderQueueSetupCmd = 0x225;
constexpr uint32_t kWmiReorderQueueSetupWords = 9;
constexpr uint32_t kStaTids = 17, kStaNonQosTid = 16;
// The receive reorder queue descriptor in host memory (128-byte aligned, the hardware's own): a 32-word queue descriptor and,
// for a QoS identifier, three 32-word extension descriptors (enough for a window of 256). Word 0 of each is its header: the
// owner (3:0, 4 = the reorder unit), the kind (7:4: 8 a queue, 9 an extension) and a debug pattern (31:8). Word 1 the queue
// number (15:0). Word 2: valid (0), which link-descriptor counter (2:1, 1), the access category (6:5), retry check (8), the
// window size less one (20:11), PN check (21), PN size (26:25), "ignore the A-MPDU flag" (27). Word 3: the start sequence
// number (12:1). A window of 1 on a QoS identifier is written as 2 (the hardware's rule); a window of 1 on the non-QoS
// identifier sets the retry check instead.
constexpr uint32_t kReoQueueAlign = 128, kReoQueueWords = 32, kReoQueueExtWords = 32, kReoQueueExtCount = 3;
constexpr uint32_t kReoQueueQosBytes = (kReoQueueWords + kReoQueueExtCount * kReoQueueExtWords) * 4;   // 512
constexpr uint32_t kReoQueueNonQosBytes = kReoQueueWords * 4;                                          // 128
constexpr uint32_t kReoDescOwnerReo = 4, kReoDescTypeQueue = 8, kReoDescTypeQueueExt = 9;
constexpr uint32_t kReoQueueMagic0 = 0xddbeef, kReoQueueMagic1 = 0xadbeef, kReoQueueMagic2 = 0xbdbeef,
                   kReoQueueMagic3 = 0xcdbeef;
constexpr uint32_t kReoQueueVld = 1u << 0, kReoQueueAssocLinkCounterShift = 1, kReoQueueAcShift = 5, kReoQueueRetry = 1u << 8,
                   kReoQueueBaWindowShift = 11, kReoQueueBaWindowMask = 0x3ffu, kReoQueuePnCheck = 1u << 21,
                   kReoQueuePnSizeShift = 25, kReoQueueIgnoreAmpdu = 1u << 27, kReoQueueSsnShift = 1, kReoQueueSsnMask = 0xfffu;
// The firmware's data interface names a created peer: HTT_T2H peer map (3; the second and third forms 0x1e, 0x2b with the
// hardware peer identifier in other places), word 0 the type (7:0), the device (15:8) and the peer identifier (31:16), word 1
// the address's first four bytes, word 2 its last two (15:0) and (forms 3 and 0x1e) the hardware peer (31:16); unmap is 4 / 0x1f.
constexpr uint32_t kHttT2hPeerUnmap = 0x04, kHttT2hPeerMap2 = 0x1e, kHttT2hPeerUnmap2 = 0x1f, kHttT2hPeerMap3 = 0x2b;
// The events level 7 waits for besides those above: the device stopped, a peer deleted, a roam event (the firmware's beacon
// miss among its reasons), each with its tag.
constexpr uint32_t kWmiTagRoamEvent = 0x030;
constexpr uint32_t kWmiEvtRoam = 0x0b001;
constexpr uint32_t kWmiRoamReasonMask = 0xf, kWmiRoamReasonBeaconMiss = 2;
// 802.11 element and capability facts the association request needs: the band's rates (500 kb/s units; the CCK ones 1, 2,
// 5.5 and 11 Mb/s are 2, 4, 11 and 22), the TIM element's DTIM period, the vendor element of WPA1 (00:50:F2 type 1), spectrum
// management (capability bit 8: the access point wants the power capability and the supported channels elements), and the
// status codes the log names.
constexpr uint16_t kDot11CapSpectrumMgmt = 0x0100, kDot11CapQos = 0x0200;
constexpr uint32_t kDot11ElementPowerCap = 33, kDot11ElementSupportedChannels = 36, kDot11ElementHtCap = 45, kDot11ElementHtOperation = 61,
                   kDot11ElementVendor = 221;
constexpr uint32_t kDot11AuthRespSeq = 2, kDot11AssocRespFixed = 6;
constexpr uint16_t kDot11StatusSuccess = 0;
constexpr uint32_t kStaFrameSeqShift = 4;
constexpr uint32_t kStaListenInterval = kAssocListenInterval;   // what the association request and the peer's association say

// ---- level 8, the data path (WifiDp.h; docs/drivers/wifi.md §13.6) ----
// Facts of the Ubuntu tree of §3 for WCN7860, which takes QCC2072's HAL and registers and WCN7850's transmit-ring map
// (wifi7/hal.c, wifi7/hal_qcc2072.c, wifi7/hal.h, wifi7/hal_desc.h, wifi7/hal_rx_desc.h, wifi7/dp_tx.c, wifi7/dp_rx.c, dp.c,
// dp_htt.[ch], hal.h): register offsets, ring identifiers, field places and bit positions, read for those facts only.
//
// The rings the host programs itself (the UMAC's "SRNG" rings, the copy engine's register layout: base low, base high | size
// in words << 8, ring identifier << 8 | entry words, misc at +0x10 (bit 6 enable, bit 1 no loop count for a source ring, bit 0
// no ring identifier for the idle link ring), the other side's pointer in host memory at +0x1c/+0x20 (source) or +0x14/+0x18
// (destination); the host's own pointer in the R2 group, +4 the tail for a destination ring):
//   TCL data 1 (host -> TCL, the transmit ring): R0 0x918, R2 0x2000 of the TCL unit, 8-word entries
//   WBM2SW0 (its completions; TCL ring 0 returns its buffers there, manager "software 0"), WBM2SWn at +0x78 * n, R2 +8 * n
//   WBM2SW3 (released receive buffers: the receive error ring of this chip's host; WBM2SW1 is never programmed, as that host does)
//   REO2SW1 (received MSDUs, reordered), REO2SW0 (the reorder unit's exceptions, fragments and BARs), 8-word entries
//   WBM idle link (host -> WBM: the link descriptors REO and the receive DMA build their lists from), 2-word entries
constexpr uint32_t kDpTcl1R0 = kUnitTcl + 0x918, kDpTcl1R2 = kUnitTcl + 0x2000;
constexpr uint32_t kDpWbm2Sw0R0 = kUnitWbm + 0xe08, kDpWbm2Sw0R2 = kUnitWbm + 0x30c8;
constexpr uint32_t kDpWbm2SwR0Stride = 0xe80 - 0xe08, kDpWbm2SwR2Stride = 8;
constexpr uint32_t kDpReo2Sw1R0 = kUnitReo + 0x500, kDpReo2Sw1R2 = kUnitReo + 0x3048;
constexpr uint32_t kDpReo2Sw0R0 = kUnitReo + 0x8c0, kDpReo2Sw0R2 = kUnitReo + 0x3088;
constexpr uint32_t kDpIdleLinkR0 = kUnitWbm + 0xd3c, kDpIdleLinkR2 = kUnitWbm + 0x30b8;
constexpr uint32_t kDpRingIdReo2Sw0 = 0, kDpRingIdReo2Sw1 = 1, kDpRingIdWbm2Sw0 = 128;
// The rest of the Peach ring fabric, from hw_srng_table_peach in the real qca_cld3_peach_v2.ko (2026-11-28: the table sits at
// 0x121b0 in its .data, 28 entries of 36 bytes). The missing pieces the OEM driver initializes and we did not.
constexpr uint32_t kDpSw2WbmR0 = kUnitWbm + 0x37c, kDpSw2WbmR2 = kUnitWbm + 0x3010;
constexpr uint32_t kDpReoCmdR0 = kUnitReo + 0x2a8, kDpReoCmdR2 = kUnitReo + 0x3020;
constexpr uint32_t kDpReoStatusR0 = kUnitReo + 0xaa0, kDpReoStatusR2 = kUnitReo + 0x30a8;
constexpr uint32_t kDpReoReinjectR0 = kUnitReo + 0x320, kDpReoReinjectR2 = kUnitReo + 0x3028;
constexpr uint32_t kDpRingIdSw2Wbm = 121, kDpRingIdReoCmd = 20, kDpRingIdReoStatus = 21, kDpRingIdReoReinject = 16;
constexpr uint32_t kDpReoCmdEntryWords = 10, kDpReoStatusEntryWords = 28;
constexpr uint32_t kDpTclEntryWords = 8, kDpWbmEntryWords = 8, kDpReoEntryWords = 8, kDpIdleEntryWords = 2;
constexpr uint32_t kRingMiscNoRingId = 1u << 0;
// The reorder unit's own set-up (this chip's host, at its start): REO1_GEN_ENABLE (+0) gains the aging list and the aging
// flush (bits 2, 3); MISC_CTRL (+0xba0) sends fragments (20:17) and BARs (24:21) to REO2SW0; the four aging thresholds
// (+0xb2c..+0xb38, microseconds: 100 ms for BE/BK/VI, 40 ms for VO); and the 32 hash entries of DEST_RING_CTRL_IX_2/IX_3
// (+0xc, +0x10: four bits each, 1 = REO2SW1) all to the one ring this host reads.
constexpr uint32_t kDpReoGenEnable = kUnitReo + 0x0, kDpReoMiscCtrl = kUnitReo + 0xba0, kDpReoAgingIx0 = kUnitReo + 0xb2c;
constexpr uint32_t kDpReoDestIx2 = kUnitReo + 0x0c, kDpReoDestIx3 = kUnitReo + 0x10;
constexpr uint32_t kDpReoGenAgingList = 1u << 2, kDpReoGenAgingFlush = 1u << 3;
constexpr uint32_t kDpReoMiscFragMask = 0xfu << 17, kDpReoMiscBarMask = 0xfu << 21;
constexpr uint32_t kDpReoAgingBeUs = 100 * 1000, kDpReoAgingVoUs = 40 * 1000;
constexpr uint32_t kDpReoHashAllSw1 = 0x11111111u;
// The transmit "bank" registers (the TCL's per-bank configuration, 0xa4408c + 4 * bank): EPD (0), encapsulation (2:1: 0 raw,
// 1 native Wi-Fi, 2 Ethernet), encryption (6:3), index lookup (9), address X search (10), address Y search (11), mesh (13:12),
// vdev identifier check (14), radio (16:15). A station's bank: Ethernet, index lookup, address Y search, the vdev check.
constexpr uint32_t kDpTclBankConfig = 0x00a4408c;
constexpr uint32_t kDpBankEncapEthernet = 2u << 1, kDpBankIndexLookup = 1u << 9, kDpBankAddrY = 1u << 11,
                   kDpBankVdevCheck = 1u << 14;
constexpr uint32_t kDpBankStation = kDpBankEncapEthernet | kDpBankIndexLookup | kDpBankAddrY | kDpBankVdevCheck;
// A transmit descriptor (TCL data command, 8 words): the buffer (address low; address high 7:0, its manager 11:8 = 5 "software
// 0", a cookie of ours 31:12); info0 (desc type 1: 0 a buffer, bank 7:2); info1 the TCL metadata in 31:16 (type 1 "vdev
// based" 1:0, vdev 10:3, radio 12:11); info2 the length (15:0), "to firmware" (21), the packet offset (31:23); info3 "overwrite
// the TID" (0), the TID (7:4), the radio (10:9), the vdev (31:24); info4 the search index (19:0) and the cache set (23:20);
// info5 0.
constexpr uint32_t kDpRbmSw0 = 5, kDpRbmSw1 = 6, kDpRbmIdleDescDev0 = 1;
constexpr uint32_t kDpTclBankShift = 2, kDpTclCmdNumShift = 16, kDpTclVdevShift = 24, kDpTclTidShift = 4, kDpTclPmacShift = 9;
constexpr uint32_t kDpTclTidOverwrite = 1u << 0, kDpTclToFw = 1u << 21, kDpTclCacheSetShift = 20;
constexpr uint32_t kDpTclMetaVdevType = 1, kDpTclMetaVdevShift = 3, kDpTclMetaPdevShift = 11;
// A WBM release entry (8 words, no cookie conversion): the buffer address info (the cookie in 31:12 of word 1, the manager in
// 11:8), info0 the release source (2:0: 0 TQM, 1 receive DMA, 2 REO, 3 firmware, 4 software), the descriptor type (8:6), the
// TQM's reason (18:13 for a transmit completion: 0 acknowledged), the REO's push reason (25:24) and error (30:26).
// A transmit completion on WBM2SW0 has the same first words (the buffer's address info, as no cookie conversion runs) and the
// TQM's reason in 16:13 of info0.
constexpr uint32_t kDpRelSrcMask = 0x7, kDpRelSrcTqm = 0, kDpRelSrcRxdma = 1, kDpRelSrcReo = 2, kDpRelSrcFw = 3;
constexpr uint32_t kDpTqmReasonShift = 13, kDpTqmReasonMask = 0xf;
// Cookie conversion (the hardware turning a cookie into a host address through tables in the chip's memory): this host does
// not set it up, so the release and destination entries keep the address and cookie the host wrote. Its two enables are read
// back for the log only: REO1_SW_COOKIE_CFG1 (REO + 0x70: enable 19, global enable 20) and WBM_SW_COOKIE_CONVERT_CFG (WBM +
// 0x94: WBM2SW0..4 1..5, global 8).
constexpr uint32_t kDpReoSwCookieCfg1 = kUnitReo + 0x70, kDpWbmCookieConvert = kUnitWbm + 0x94;
constexpr uint32_t kDpReoCookieEnables = (1u << 19) | (1u << 20), kDpWbmCookieEnables = 0x13e;
// A REO destination entry (8 words): the MSDU buffer's address info (word 0-1: the cookie), the MPDU info (word 2: MSDU count
// 7:0), the peer's metadata (word 3), the MSDU info (word 4: first 0, last 1, continuation 2, length 16:3), two words of a
// converted address (unused here), info0 (word 7: buffer type 0, push reason 2:1, error 7:3, ring 27:20).
constexpr uint32_t kDpMsduFirst = 1u << 0, kDpMsduLast = 1u << 1, kDpMsduContinuation = 1u << 2;
constexpr uint32_t kDpMsduLenShift = 3, kDpMsduLenMask = 0x3fff;
constexpr uint32_t kDpReoBufTypeLinkDesc = 1u << 0, kDpReoPushShift = 1, kDpReoErrShift = 3;
// The receive buffer: QCC2072's descriptor (392 bytes) and then the frame at 392 + the L3 padding. In it: msdu_end's tag at 0
// and its fields from 4 — info5 (16 bits at 46: L3 padding 11:10, first MSDU 12, last MSDU 13), info10 (at 76: the MSDU length
// 13:0), info11 (at 80: the decapsulation 9:8: 0 raw, 1 native Wi-Fi, 2 Ethernet II, 3 802.3), info13 (at 124: multicast or
// broadcast 2, null data 7, A-MSDU error 12, overflow 16, MSDU length error 17, MPDU length error 27, TKIP MIC 28, decryption
// 29, FCS 31),
// info14 (at 128: the decryption status 12:10, MSDU done 31); mpdu_start's tag at 140, its info2 at 148 (the TID 18:15), info4
// at 176, the software peer at 186; the 802.11 header's TLV at 264.
constexpr uint32_t kRxDescBytes = 392, kRxDescInfo5 = 46, kRxDescInfo10 = 76, kRxDescInfo11 = 80, kRxDescInfo13 = 124,
                   kRxDescInfo14 = 128, kRxDescMpduInfo2 = 148, kRxDescPeerId = 186;
constexpr uint32_t kRxDescMsduEndTag = 0, kRxDescMpduStartTag = 140, kRxDescPktHdr = 264;
constexpr uint32_t kRxDescL3PadShift = 10, kRxDescL3PadMask = 0x3, kRxDescFirstMsdu = 1u << 12, kRxDescLastMsdu = 1u << 13;
constexpr uint32_t kRxDescMsduLenMask = 0x3fff, kRxDescDecapShift = 8, kRxDescDecapMask = 0x3;
constexpr uint32_t kRxDescMcbc = 1u << 2, kRxDescNullData = 1u << 7;
constexpr uint32_t kRxDescErrors = (1u << 31) | (1u << 29) | (1u << 28) | (1u << 27) | (1u << 17) | (1u << 16) | (1u << 12);
constexpr uint32_t kRxDescMsduDone = 1u << 31, kRxDescTidShift = 15, kRxDescTidMask = 0xf;
constexpr uint32_t kRxDecapRaw = 0, kRxDecapNativeWifi = 1, kRxDecapEthernet = 2, kRxDecap8023 = 3;
// The receive DMA's ring selection (HTT_H2T 0x0c, 18 words), as this chip's host sends it for each radio buffer ring: word 0
// the type, the radio + 1 (15:8), the ring (23:16: 0 the radio's buffer ring), "offsets valid" (26) and "monitor enabled" (28,
// the host leaves it on); word 1 the buffer size (15:0); words 2-5 the frame filters (none for management, BAR for control in
// word 4 bit 24, multicast, unicast and null data in word 5 bits 18, 21, 24); word 6 the TLVs (MPDU start 0, packet 2, MSDU
// end 3); word 7 the packet's offset (15:0) and the 802.11 header's (31:16); word 8 the MPDU start's (31:16); word 9 the MSDU
// end's (15:0); the rest 0.
constexpr uint32_t kHttRxSelectionWords = 18;
constexpr uint32_t kHttRxSelOffsetValid = 1u << 26, kHttRxSelRxMon = 1u << 28;
constexpr uint32_t kHttRxSelCtrlBar = 1u << 24;
constexpr uint32_t kHttRxSelDataMcast = 1u << 18, kHttRxSelDataUcast = 1u << 21, kHttRxSelDataNull = 1u << 24;
constexpr uint32_t kHttRxSelTlvs = (1u << 0) | (1u << 2) | (1u << 3);
// The 802.1X frames (EAPOL) of the four-way handshake: Ethernet type 0x888e.
constexpr uint16_t kEtherTypeEapol = 0x888e;
// The radio's identifier the data path names (the transmit metadata's radio field): a chip of this family that runs as one
// radio (both bands on one device, as this one does) has its host name radio 0 whatever the capability event's entries say.
constexpr uint32_t kDpPdevSingle = 0;

}  // namespace pianowifi
