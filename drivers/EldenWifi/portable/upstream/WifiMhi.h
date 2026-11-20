// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 4: the firmware into the WCN7860 over MHI, as a portable state machine the owner steps (host tests:
// tests/wifi_host.cpp). Design re-expressed from UniXNU-sheng `package/MhiBoot.c/h` and PaganiWifi `MhiBoot.c`, `WifiMhiLoad.c`
// (both BSD-2-Clause-Patent; UPSTREAM records which), in this namespace and with piano's facts from WifiHw.h; the registers and
// their bits are hardware facts (mainline's MHI host is read for behaviour only, never copied).
//
// What level 4 does: BAR0 carries the MHI register block at offset 0. The device reports where its boot host interface (BHI) and
// its vector interface (BHIe) are. The boot:
//   1. the execution environment must be the primary boot loader (PBL) or EDL; a device in a system error is reset first;
//   2. BHI takes the secondary boot loader: the firmware file's first 512 KiB, in one physically contiguous buffer;
//   3. the device reports READY; the host gives it its MHI context arrays and asks for M0;
//   4. the secondary boot loader runs (EE = SBL); BHIe takes the rest of the image as a table of 512 KiB segments;
//   5. the device reaches mission mode (EE = AMSS). Level 4 stops there: channels, QRTR and QMI are level 5 and up.
// The firmware file is read at run time from the tablet's own `modem_a` FAT (`image/peach/amss20.bin`); nothing is ever staged in
// this repository, and the image is dropped from memory when level 4 ends.
#pragma once
#include <stdint.h>
#include "WifiHw.h"

namespace pianowifi {

// ---------------------------------------------------------------------------------------------- the firmware file's two parts
// The secondary boot loader is the file's first `sblBytes` bytes. On peach a second ELF follows it, and BHIe carries only that
// second ELF; on WCN7850 the file is one image and BHIe carries all of it. The test is the four bytes at `sblBytes` (facts: the
// vendor MHI host's `tme_supported_image` and mainline's firmware loader both look at exactly that).
struct FwLayout {
  uint32_t sblOffset = 0, sblBytes = 0, imageOffset = 0, imageBytes = 0;
  bool split = false;
};
constexpr unsigned kElfMagicBytes = 4;
inline bool firmwareLayout(const uint8_t *head, uint32_t headBytes, uint32_t bytes, uint32_t sblBytes, FwLayout &out)
{
  if (!bytes || !sblBytes) return false;
  out.sblOffset = 0;
  out.sblBytes = bytes < sblBytes ? bytes : sblBytes;
  out.imageOffset = 0;
  out.imageBytes = bytes;
  out.split = false;
  if (bytes <= sblBytes || bytes - out.sblBytes < kElfMagicBytes) return true;
  if (!head || headBytes < sblBytes + kElfMagicBytes) return false;
  const uint8_t *at = head + sblBytes;
  if (at[0] == 0x7f && at[1] == 'E' && at[2] == 'L' && at[3] == 'F') {
    out.imageOffset = sblBytes;
    out.imageBytes = bytes - sblBytes;
    out.split = true;
  }
  return true;
}

// The same rule when the caller has only the four bytes at `sblBytes` (the kext reads them from the file, so that no 7 MiB copy of
// the image is ever on the heap): `magic` is those four bytes, or a null pointer when the file ends before them.
inline bool firmwareLayoutFromMagic(const uint8_t *magic, uint32_t bytes, uint32_t sblBytes, FwLayout &out)
{
  if (!bytes || !sblBytes) return false;
  out.sblOffset = 0;
  out.sblBytes = bytes < sblBytes ? bytes : sblBytes;
  out.imageOffset = 0;
  out.imageBytes = bytes;
  out.split = false;
  if (bytes <= sblBytes || bytes - out.sblBytes < kElfMagicBytes) return true;
  if (!magic) return false;
  if (magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F') {
    out.imageOffset = sblBytes;
    out.imageBytes = bytes - sblBytes;
    out.split = true;
  }
  return true;
}

// ---------------------------------------------------------------------------------------------- a DMA arena (bump allocator)
// One physically contiguous window the owner maps non-cacheable; the endpoint's stream bypasses the SMMU, so a bus address is the
// physical address. Every buffer starts on a boundary of its own size rounded up to a power of two, at least 64 bytes and at least
// a page from 4 KiB on: SHENG saw the boot loader refuse an image buffer that was only page aligned.
struct Arena {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t bytes = 0, used = 0, allocations = 0, failures = 0;
};
inline uint64_t arenaAlign(uint64_t n)
{
  uint64_t a = 64;
  while (a < n) a <<= 1;
  return a;
}
inline void arenaInit(Arena &a, uint8_t *va, uint64_t bus, uint32_t bytes)
{
  a = Arena{va, bus, bytes, 0, 0, 0};
}
inline uint8_t *arenaAlloc(Arena &a, uint32_t n, uint64_t *bus)
{
  if (!a.va || !n) { ++a.failures; return nullptr; }
  const uint64_t align = arenaAlign(n);
  const uint64_t at = (a.bus + a.used + align - 1) & ~(align - 1);
  const uint64_t offset = at - a.bus;
  if (offset + n > a.bytes) { ++a.failures; return nullptr; }
  a.used = uint32_t(offset + n);
  ++a.allocations;
  if (bus) *bus = at;
  uint8_t *p = a.va + offset;
  // Zeroed eight bytes at a time (the start is aligned to at least 64 bytes, so only the tail is byte-wise): level 5 asks for
  // regions of several MiB, and the window is reached through a write-combined mapping where a byte-wise loop is very slow.
  uint32_t i = 0;
  for (; i + 8 <= n; i += 8) *reinterpret_cast<uint64_t *>(p + i) = 0;
  for (; i < n; ++i) p[i] = 0;
  return p;
}

// ---------------------------------------------------------------------------------------------------- the boot state machine
enum MhiPhase : uint32_t {
  kMhiIdle, kMhiResetting, kMhiSblLoading, kMhiWaitReady, kMhiNeedContexts, kMhiWaitSbl, kMhiImageLoading, kMhiWaitMission,
  kMhiDone, kMhiFailed,
};
enum MhiFail : uint32_t {
  kMhiErrNone, kMhiErrLayout, kMhiErrNotPbl, kMhiErrBhi, kMhiErrBhie, kMhiErrSysErr, kMhiErrTimeout, kMhiErrState, kMhiErrRddm,
};
enum MhiEe : uint32_t { kEePbl = 0, kEeSbl = 1, kEeAmss = 2, kEeRddm = 3, kEeWfw = 4, kEePthru = 5, kEeEdl = 6, kEeFp = 7 };
enum MhiState : uint32_t {
  kStateReset = 0, kStateReady = 1, kStateM0 = 2, kStateM1 = 3, kStateM2 = 4, kStateM3 = 5, kStateBhi = 7, kStateSysErr = 0xff,
};

inline const char *mhiPhaseName(uint32_t phase)
{
  switch (phase) {
  case kMhiIdle: return "idle";
  case kMhiResetting: return "resetting";
  case kMhiSblLoading: return "boot loader over BHI";
  case kMhiWaitReady: return "waiting for READY";
  case kMhiNeedContexts: return "contexts needed";
  case kMhiWaitSbl: return "waiting for the boot loader to run";
  case kMhiImageLoading: return "image over BHIe";
  case kMhiWaitMission: return "waiting for mission mode";
  case kMhiDone: return "mission mode";
  default: return "failed";
  }
}
inline const char *mhiEeName(uint32_t ee)
{
  switch (ee) {
  case kEePbl: return "PBL";
  case kEeSbl: return "SBL";
  case kEeAmss: return "AMSS (mission mode)";
  case kEeRddm: return "RDDM (crash dump)";
  case kEeWfw: return "WFW";
  case kEePthru: return "PTHRU";
  case kEeEdl: return "EDL";
  case kEeFp: return "FP";
  default: return "?";
  }
}
inline const char *mhiFailName(uint32_t error)
{
  switch (error) {
  case kMhiErrNone: return "none";
  case kMhiErrLayout: return "the register layout is not usable";
  case kMhiErrNotPbl: return "the device is not in its primary boot loader";
  case kMhiErrBhi: return "BHI reported an error";
  case kMhiErrBhie: return "BHIe reported an error";
  case kMhiErrSysErr: return "the device reported a system error";
  case kMhiErrTimeout: return "a phase timed out";
  case kMhiErrState: return "a step was asked for in the wrong phase";
  default: return "the device went to its crash dump environment";
  }
}

struct MhiIo {
  void *ctx = nullptr;
  uint32_t (*read)(void *ctx, uint32_t reg) = nullptr;
  void (*write)(void *ctx, uint32_t reg, uint32_t value) = nullptr;   // completes with a barrier
};

struct MhiBoot {
  MhiIo io;
  uint32_t space = 0, reglen = 0, bhi = 0, bhie = 0;
  uint32_t phase = kMhiFailed, error = kMhiErrNone, failedPhase = 0;
  uint32_t ee = 0, state = 0, seq = 0, errcode = 0, lastStatus = 0;
  uint32_t errdbg[3] = {0, 0, 0};           // BHI's three error debug words, read with the error code
  // BHI's status as found before the boot loader's address was written, and right after this host wrote 0 to it: the register's
  // power-on value is undefined, so an error read later counts only if the clear took or the value changed since. (piano,
  // 2026-11-12: the morning's boots ended with ffffffff / ef0e0003 and were taken for untouched power-on contents; wifi-3a and 3b
  // read 0 before the clear and saw the boot loader itself write ffffffff / ef0e0003 45 ms after the doorbell.)
  uint32_t statusBefore = 0, statusCleared = 0;
  bool clearTook = false;
  uint64_t sblBus = 0, tableBus = 0;
  uint32_t sblBytes = 0, tableBytes = 0, msiVector = 0;
};

namespace mhidetail {
inline uint32_t rd(MhiBoot &m, uint32_t reg) { return m.io.read(m.io.ctx, reg); }
inline void wr(MhiBoot &m, uint32_t reg, uint32_t value) { m.io.write(m.io.ctx, reg, value); }
inline uint32_t fail(MhiBoot &m, uint32_t error)
{
  m.failedPhase = m.phase;
  m.error = error;
  m.phase = kMhiFailed;
  return m.phase;
}
inline void readErrors(MhiBoot &m)
{
  m.errcode = rd(m, m.bhi + kBhiErrCode);
  m.errdbg[0] = rd(m, m.bhi + kBhiErrDbg1);
  m.errdbg[1] = rd(m, m.bhi + kBhiErrDbg2);
  m.errdbg[2] = rd(m, m.bhi + kBhiErrDbg3);
}
// The boot loader's image over BHI, in the order this chip family's own host writes it: the status cleared, the address high then
// low, the size, then the doorbell with the session's sequence number (never 0).
inline uint32_t startSbl(MhiBoot &m)
{
  wr(m, m.bhi + kBhiIntVec, m.msiVector);   // a reset clears it
  m.statusBefore = rd(m, m.bhi + kBhiStatus);
  wr(m, m.bhi + kBhiStatus, 0);
  m.statusCleared = rd(m, m.bhi + kBhiStatus);
  m.clearTook = m.statusCleared >> 30 != kMhiXferError;
  wr(m, m.bhi + kBhiImgAddrHi, uint32_t(m.sblBus >> 32));
  wr(m, m.bhi + kBhiImgAddrLo, uint32_t(m.sblBus));
  wr(m, m.bhi + kBhiImgSize, m.sblBytes);
  wr(m, m.bhi + kBhiImgTxDb, m.seq);
  m.phase = kMhiSblLoading;
  return m.phase;
}
inline uint32_t startImage(MhiBoot &m)
{
  m.seq = (m.seq + 1) & kMhiSeqMask;
  if (!m.seq) m.seq = 1;
  wr(m, m.bhie + kBhieTxVecAddrHi, uint32_t(m.tableBus >> 32));
  wr(m, m.bhie + kBhieTxVecAddrLo, uint32_t(m.tableBus));
  wr(m, m.bhie + kBhieTxVecSize, m.tableBytes);
  wr(m, m.bhie + kBhieTxVecDb, m.seq);
  m.phase = kMhiImageLoading;
  return m.phase;
}
}  // namespace mhidetail

inline uint32_t mhiEeRead(MhiBoot &m) { return m.ee = mhidetail::rd(m, m.bhi + kBhiExecEnv); }
inline uint32_t mhiStateRead(MhiBoot &m)
{
  return m.state = (mhidetail::rd(m, kMhiStatus) >> kMhiStateShift) & 0xffu;
}

// Reads the register layout; false when the boot interfaces do not lie inside the register space the owner mapped.
inline bool mhiOpen(MhiBoot &m, const MhiIo &io, uint32_t space)
{
  renew(m);
  m.io = io;
  m.space = space;
  m.reglen = space ? space : mhidetail::rd(m, kMhiRegLen);
  m.bhi = mhidetail::rd(m, kMhiBhiOff);
  m.bhie = mhidetail::rd(m, kMhiBhieOff);
  // The owner's mapping bounds the space (piano's BAR0 is 2 MiB, wifi-l4 2026-11-12); MHIREGLEN alone is trusted up to 1 MiB.
  const bool good = m.reglen >= 0x100 && m.reglen <= (space ? 0x1000000u : 0x100000u) && m.bhi >= 0x100 && m.bhi + kBhiErrCode + 4 <= m.reglen &&
                    m.bhie >= 0x100 && m.bhie + kBhieTxVecStatus + 4 <= m.reglen && !(m.bhi & 3) && !(m.bhie & 3);
  if (!good) {
    m.phase = kMhiFailed;
    m.error = kMhiErrLayout;
    return false;
  }
  m.phase = kMhiIdle;
  return true;
}

// The receive vector block (BHIe + 0x60 .. + 0x78: the crash dump table's address, size, doorbell and status) zeroed word by word,
// as the MHI host does before every power-up of a device with a crash dump: their power-on values are undefined (piano's read
// 74bf67da:e7bbfbc5 ... f10d0db2 on 2026-11-12). Returns the number of words written.
inline unsigned mhiClearRxVectors(MhiBoot &m)
{
  if (m.phase != kMhiIdle || !m.bhie || m.bhie + kBhieRxVecStatus + 4 > m.reglen) return 0;
  unsigned n = 0;
  for (uint32_t off = kBhieRxVecAddrLo; off <= kBhieRxVecStatus; off += 4, ++n) mhidetail::wr(m, m.bhie + off, 0);
  return n;
}

// One BHIe vector table entry, as the device reads it (little endian).
struct BhieEntry { uint64_t address, size; };
inline uint32_t bhieTable(BhieEntry *table, uint32_t count, const uint64_t *addresses, uint32_t imageBytes, uint32_t segmentBytes)
{
  if (!table || !segmentBytes || !imageBytes) return 0;
  const uint32_t needed = (imageBytes + segmentBytes - 1) / segmentBytes;
  if (needed > count) return 0;
  for (uint32_t i = 0; i < needed; ++i) {
    const uint32_t left = imageBytes - i * segmentBytes;
    table[i].address = addresses[i];
    table[i].size = left < segmentBytes ? left : segmentBytes;
  }
  return needed;
}

inline uint32_t mhiBegin(MhiBoot &m, uint32_t msiVector, uint64_t sblBus, uint32_t sblBytes, uint64_t tableBus, uint32_t tableBytes,
                         uint32_t seq)
{
  using namespace mhidetail;
  if (m.phase != kMhiIdle) return fail(m, kMhiErrState);
  m.msiVector = msiVector;
  m.sblBus = sblBus;
  m.sblBytes = sblBytes;
  m.tableBus = tableBus;
  m.tableBytes = tableBytes;
  m.seq = seq & kMhiSeqMask;
  if (!m.seq) m.seq = 1;
  const uint32_t ee = mhiEeRead(m);
  if (ee != kEePbl && ee != kEeEdl) return fail(m, kMhiErrNotPbl);
  const uint32_t status = rd(m, kMhiStatus);
  m.state = (status >> kMhiStateShift) & 0xffu;
  wr(m, m.bhi + kBhiIntVec, msiVector);
  if ((status & kMhiStatusSysErr) || m.state == kStateSysErr) {
    wr(m, kMhiCtrl, kMhiCtrlReset);
    m.phase = kMhiResetting;
    return m.phase;
  }
  return startSbl(m);
}

// Re-reads what the phase waits for and moves on. All ones from MHI_STATUS means the device is not answering (its PCIe core is
// restarting while its boot loader starts): not a status, so the phase stands and the owner's deadline decides. BHI's status is
// read as this chip family's host reads it: bits 31:30 at 3 are an error, all ones included, as long as MHI_STATUS answers and the
// value is not the power-on one this host could not clear (statusBefore / clearTook above).
inline uint32_t mhiStep(MhiBoot &m)
{
  using namespace mhidetail;
  if (m.phase == kMhiIdle || m.phase == kMhiDone || m.phase == kMhiFailed || m.phase == kMhiNeedContexts) return m.phase;
  const uint32_t status = rd(m, kMhiStatus);
  if (status == 0xffffffffu) return m.phase;
  m.state = (status >> kMhiStateShift) & 0xffu;
  if (m.phase == kMhiResetting) {
    if (rd(m, kMhiCtrl) & kMhiCtrlReset) return m.phase;
    return startSbl(m);
  }
  const uint32_t ee = mhiEeRead(m);
  if (ee == kEeRddm) return fail(m, kMhiErrRddm);
  if ((status & kMhiStatusSysErr) || m.state == kStateSysErr) return fail(m, kMhiErrSysErr);
  switch (m.phase) {
  case kMhiSblLoading: {
    const uint32_t bhi = rd(m, m.bhi + kBhiStatus);
    m.lastStatus = bhi;
    if (bhi >> 30 == kMhiXferError) {
      if (bhi == 0xffffffffu && rd(m, kMhiStatus) == 0xffffffffu) return m.phase;   // the link went away between the two reads
      if (!m.clearTook && bhi == m.statusBefore) return m.phase;                     // the stale power-on value
      readErrors(m);
      return fail(m, kMhiErrBhi);
    }
    if (bhi >> 30 != kMhiXferSuccess) return m.phase;
    m.phase = kMhiWaitReady;
    return mhiStep(m);
  }
  case kMhiWaitReady:
    if ((rd(m, kMhiCtrl) & kMhiCtrlReset) || !(status & kMhiStatusReady)) return m.phase;
    m.phase = kMhiNeedContexts;
    return m.phase;
  case kMhiWaitSbl:
    if (ee == kEeAmss || ee == kEeWfw) { m.phase = kMhiDone; return m.phase; }   // the device already had the full image
    if (ee != kEeSbl) return m.phase;
    return startImage(m);
  case kMhiImageLoading: {
    const uint32_t tx = rd(m, m.bhie + kBhieTxVecStatus);
    m.lastStatus = tx;
    if ((tx & kMhiSeqMask) != m.seq) return m.phase;   // not this transfer's status yet
    if (tx >> 30 == kMhiXferError) return fail(m, kMhiErrBhie);
    if (tx >> 30 != kMhiXferSuccess) return m.phase;
    m.phase = kMhiWaitMission;
    return mhiStep(m);
  }
  case kMhiWaitMission:
    if (ee == kEeAmss || ee == kEeWfw) m.phase = kMhiDone;
    return m.phase;
  default:
    return m.phase;
  }
}

// The owner programmed the contexts (phase kMhiNeedContexts): asks for M0 and waits for the secondary boot loader.
inline uint32_t mhiContextsDone(MhiBoot &m)
{
  using namespace mhidetail;
  if (m.phase != kMhiNeedContexts) return fail(m, kMhiErrState);
  wr(m, kMhiCtrl, (rd(m, kMhiCtrl) & ~(0xffu << kMhiStateShift) & ~kMhiCtrlReset) | uint32_t(kStateM0) << kMhiStateShift);
  m.phase = kMhiWaitSbl;
  return mhiStep(m);
}

inline uint32_t mhiTimedOut(MhiBoot &m)
{
  using namespace mhidetail;
  if (m.phase == kMhiIdle || m.phase == kMhiDone || m.phase == kMhiFailed) return m.phase;
  if (m.phase == kMhiSblLoading) mhidetail::readErrors(m);
  return fail(m, kMhiErrTimeout);
}

// ---------------------------------------------------------------------------------------------------- the MHI context arrays
// 128 channel contexts left disabled, two event rings (control: 32 elements on MSI vector 1; data: 256 on vector 2) and the
// primary command ring, in the arena; then the registers that point the device at them, and the host address range it may reach.
// The driver of this chip family gives the device its contexts before the boot loader starts and again once the loader has reset
// the registers (SHENG saw the loader refuse an image otherwise); since 2026-11-12 this driver gives them only at READY, as the
// MHI host does (piano-wifi-ctxearly=1 restores the early write).
//
// The layout inside the 32 KiB (2026-11-12, after wifi-4a): the channel contexts at +0, the event ring contexts at +0x2000 and the
// command ring's at +0x3000, each array on a page of its own as the MHI host allocates them; then the rings, each one's base a
// multiple of its own length (the MHI host's rule for every ring it gives a device): the control event ring (512 bytes), the data
// event ring (4 KiB) and the command ring (128 bytes). Until then the data event ring sat 512 bytes into a page, which the control
// ring and the boot loader never noticed, but channels 20 and 21 report on that ring.
// The two IPC router channels' fixed fields are written here too, as the MHI host's context initialisation writes every channel
// its configuration names before the power-up: state disabled, burst mode disabled, the type (20 to the device, 21 back) and the
// event ring they report on. Their rings and the enabled state come only when the channel is started (WifiChannels.h).
struct MhiContexts {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t bytes = 0;
  uint64_t eventBus[2] = {0, 0}, acked[2] = {0, 0};
  uint32_t eventBytes[2] = {0, 0};
  uint8_t *eventVa[2] = {nullptr, nullptr};
  uint64_t commandBus = 0;
  uint32_t writes = 0, acks = 0;
};
constexpr uint32_t kMhiContextBytes = 32 * 1024;
constexpr uint32_t kMhiContextStride = 44, kMhiChannels = 128, kMhiEventRings = 2, kMhiCommandElements = 8, kMhiElement = 16;
constexpr uint32_t kMhiEventCtxOffset = 0x2000, kMhiCommandCtxOffset = 0x3000, kMhiRingsOffset = 0x4000;
constexpr uint64_t kMhiHostLimit = (1ull << 36) - 1;   // what ath12k and the 13T's cnss2 both allow the chip to reach
// The channels whose fixed fields the plan writes: the IPC router's (WifiHw.h kChanIpcrOut / kChanIpcrIn, on the data event ring).
struct MhiChannelInit { uint32_t chan, type, eventRing; };
constexpr MhiChannelInit kMhiChannelInit[] = {
  {kChanIpcrOut, kChanTypeOutbound, kIpcrEventRing},
  {kChanIpcrIn, kChanTypeInbound, kIpcrEventRing},
};

inline uint8_t *mhiChannelCtx(const MhiContexts &c, uint32_t chan) { return c.va + chan * kMhiContextStride; }
inline uint8_t *mhiEventCtx(const MhiContexts &c, unsigned ring) { return c.va + kMhiEventCtxOffset + ring * kMhiContextStride; }
inline uint8_t *mhiCommandCtx(const MhiContexts &c) { return c.va + kMhiCommandCtxOffset; }

namespace mhidetail {
inline void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}
inline void put64(uint8_t *at, uint64_t v)
{
  put32(at, uint32_t(v));
  put32(at + 4, uint32_t(v >> 32));
}
inline uint64_t get64(const uint8_t *at)
{
  uint64_t v = 0;
  for (unsigned i = 0; i < 8; ++i) v |= uint64_t(at[i]) << (8 * i);
  return v;
}
inline void reg64(const MhiIo &io, uint32_t low, uint64_t v)
{
  io.write(io.ctx, low, uint32_t(v));
  io.write(io.ctx, low + 4, uint32_t(v >> 32));
}
// A doorbell: the high half first, since the device latches the value on the low half (as WifiChannels.h's doorbells; the owner's
// register write ends with a barrier, so the ring's memory is also out before the latching write).
inline void doorbell64(const MhiIo &io, uint32_t low, uint64_t v)
{
  io.write(io.ctx, low + 4, uint32_t(v >> 32));
  io.write(io.ctx, low, uint32_t(v));
}
// The first offset from `cursor` whose bus address is a multiple of `align` (a power of two).
inline uint32_t alignedAt(uint64_t bus, uint32_t cursor, uint32_t align)
{
  const uint64_t at = (bus + cursor + align - 1) & ~uint64_t(align - 1);
  return uint32_t(at - bus);
}
}  // namespace mhidetail

inline bool mhiContextsPlan(MhiContexts &c, uint8_t *va, uint64_t bus, uint32_t bytes)
{
  using namespace mhidetail;
  static_assert(kMhiChannels * kMhiContextStride <= kMhiEventCtxOffset, "the channel contexts reach the event contexts");
  static_assert(kMhiEventCtxOffset + kMhiEventRings * kMhiContextStride <= kMhiCommandCtxOffset, "the event contexts overlap");
  renew(c);
  c.va = va;
  c.bus = bus;
  c.bytes = bytes;
  c.eventBytes[0] = 32 * kMhiElement;
  c.eventBytes[1] = 256 * kMhiElement;
  const uint32_t commandBytes = kMhiCommandElements * kMhiElement;
  uint32_t at[kMhiEventRings] = {}, cursor = kMhiRingsOffset;
  for (unsigned i = 0; i < kMhiEventRings; ++i) {
    at[i] = alignedAt(bus, cursor, c.eventBytes[i]);
    cursor = at[i] + c.eventBytes[i];
  }
  const uint32_t commandAt = alignedAt(bus, cursor, commandBytes);
  if (!va || (bus & 4095u) || commandAt + commandBytes > bytes) return false;
  for (unsigned i = 0; i < kMhiEventRings; ++i) {
    c.eventBus[i] = bus + at[i];
    c.eventVa[i] = va + at[i];
    uint8_t *ctx = mhiEventCtx(c, i);
    put32(ctx, i == 0 ? 0 : 1u << 16);                                        // interrupt moderation: none / 1 ms
    put32(ctx + 4, 1);                                                        // the ring is valid
    put32(ctx + 8, i + 1);                                                    // MSI vector
    put64(ctx + 12, c.eventBus[i]);
    put64(ctx + 20, c.eventBytes[i]);
    put64(ctx + 28, c.eventBus[i]);                                           // read pointer
    put64(ctx + 36, c.eventBus[i] + c.eventBytes[i] - kMhiElement);           // write pointer: the whole ring is the device's
    c.acked[i] = c.eventBus[i];
  }
  c.commandBus = bus + commandAt;
  uint8_t *cmd = mhiCommandCtx(c);
  put64(cmd + 12, c.commandBus);
  put64(cmd + 20, commandBytes);
  put64(cmd + 28, c.commandBus);
  put64(cmd + 36, c.commandBus);
  for (const MhiChannelInit &ch : kMhiChannelInit) {
    uint8_t *ctx = mhiChannelCtx(c, ch.chan);
    put32(ctx + kChanCfg, kChanStateDisabled | kChanBurstDisable << 8);
    put32(ctx + kChanType, ch.type);
    put32(ctx + kChanErIndex, ch.eventRing);
  }
  return true;
}

inline void mhiContextsProgram(MhiContexts &c, const MhiIo &io, uint32_t reglen)
{
  using namespace mhidetail;
  reg64(io, kMhiCcabap, c.bus);
  reg64(io, kMhiEcabap, c.bus + kMhiEventCtxOffset);
  reg64(io, kMhiCrcbap, c.bus + kMhiCommandCtxOffset);
  reg64(io, kMhiCtrlBase, 0);
  reg64(io, kMhiCtrlLimit, kMhiHostLimit);
  reg64(io, kMhiDataBase, 0);
  reg64(io, kMhiDataLimit, kMhiHostLimit);
  io.write(io.ctx, kMhiCfg, (io.read(io.ctx, kMhiCfg) & ~0xffff0000u) | uint32_t(kMhiEventRings) << 16);
  const uint32_t erdb = io.read(io.ctx, kMhiErdbOff);
  if (erdb >= 0x100 && erdb + 8 * kMhiEventRings <= reglen && !(erdb & 3))
    for (unsigned i = 0; i < kMhiEventRings; ++i)
      doorbell64(io, erdb + 8 * i, c.eventBus[i] + c.eventBytes[i] - kMhiElement);
  ++c.writes;
}

// Gives the device back the event ring entries it filled; returns how many rings moved.
inline unsigned mhiEventAck(MhiContexts &c, const MhiIo &io, uint32_t reglen)
{
  using namespace mhidetail;
  if (!c.va) return 0;
  const uint32_t erdb = io.read(io.ctx, kMhiErdbOff);
  if (erdb < 0x100 || erdb + 8 * kMhiEventRings > reglen || (erdb & 3)) return 0;
  unsigned moved = 0;
  for (unsigned r = 0; r < kMhiEventRings; ++r) {
    uint8_t *ctx = mhiEventCtx(c, r);
    const uint64_t base = get64(ctx + 12), length = get64(ctx + 20), read = get64(ctx + 28);
    if (read == c.acked[r] || read < base || read >= base + length) continue;
    c.acked[r] = read;
    const uint64_t write = read == base ? base + length - kMhiElement : read - kMhiElement;
    put64(ctx + 36, write);
    doorbell64(io, erdb + 8 * r, write);
    ++moved;
  }
  c.acks += moved;
  return moved;
}

// ------------------------------------------------------------------------------------------- after mission mode: wake, state
// The device wake doorbell (WifiHw.h kMhiDevWakeChannel): a 64-bit doorbell like every other, the high half first. False when the
// channel doorbell array the device reports does not reach it inside the register space.
inline bool mhiDevWake(const MhiIo &io, uint32_t reglen, bool on)
{
  const uint32_t chdb = io.read(io.ctx, kMhiChdbOff);
  const uint64_t at = uint64_t(chdb) + 8u * kMhiDevWakeChannel;
  if (chdb < 0x100 || (chdb & 3) || at + 8 > reglen) return false;
  io.write(io.ctx, uint32_t(at) + 4, 0);
  io.write(io.ctx, uint32_t(at), on ? 1u : 0u);
  return true;
}
// The host's half of a state change: MHICTRL's state field (15:8) with the reset bit clear, as for M0 at READY. Level 5 uses it to
// answer a device that went to M1 with M2, which is what the MHI host does whenever the device idles.
inline void mhiSetState(const MhiIo &io, uint32_t state)
{
  const uint32_t ctrl = io.read(io.ctx, kMhiCtrl);
  io.write(io.ctx, kMhiCtrl, (ctrl & ~(0xffu << kMhiStateShift) & ~kMhiCtrlReset) | (state & 0xffu) << kMhiStateShift);
}
// What MHISTATUS and the execution environment say about a firmware that runs: dead when the device reports a system error (the
// status bit, or the state 0xff) or its crash dump environment. All ones from MHISTATUS is a device that does not answer
// (`gone`), which is neither.
struct MhiHealth {
  uint32_t status = 0, ee = 0, state = 0;
  bool sysErr = false, rddm = false, gone = false;
  bool dead() const { return sysErr || rddm; }
};
inline MhiHealth mhiHealth(const MhiIo &io, uint32_t bhiOff)
{
  MhiHealth h;
  h.status = io.read(io.ctx, kMhiStatus);
  if (h.status == 0xffffffffu) {
    h.gone = true;
    return h;
  }
  h.state = (h.status >> kMhiStateShift) & 0xffu;
  h.ee = bhiOff ? io.read(io.ctx, bhiOff + kBhiExecEnv) : 0;
  h.sysErr = (h.status & kMhiStatusSysErr) || h.state == kStateSysErr;
  h.rddm = h.ee == kEeRddm;
  return h;
}

}  // namespace pianowifi
