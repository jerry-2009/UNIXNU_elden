// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 8, the data path: the rings the host programs itself and the frames that go through them — a portable piece
// the owner steps from the ladder's thread (host tests: tests/dp_host.cpp, against a model of the chip's rings). New code for
// this repository; the registers, ring identifiers, descriptor layouts and bit positions are WifiHw.h's (§13.6), facts of the
// Ubuntu tree of docs/drivers/wifi.md §3 for WCN7860 (QCC2072's HAL), read for those facts only — no code, comment or table of
// it is here.
//
// The rings (all in the 32-bit window; each the copy engine's register layout, programmed through the chip window):
//   transmit      TCL data ring 1 (host -> TCL), its completions on WBM2SW0: a frame of en0 (802.3) goes out as one
//                 descriptor naming a transmit buffer of ours; its completion gives the buffer back
//   receive       REO2SW1: every received MSDU of our peer, reordered (the hash steering of the reorder unit all to this ring);
//                 REO2SW0: the reorder unit's exceptions (counted and passed over); WBM2SW3, the receive error ring: receive
//                 buffers the hardware released (given back); the WBM idle link ring and its link descriptors (the lists the
//                 receive DMA and the reorder unit build). WBM2SW1 is left alone: this chip's own host never programs it (the
//                 buffers' manager "software ring 1" names them as the host's, the releases come on ring 3), and a ring the
//                 firmware may own is not ours to reprogram.
//   refill        the data interface's refill ring (WifiHtt.h): every receive buffer that comes back is posted again, so the
//                 radio never runs dry (before level 8 the 511 buffers were handed out once)
// Received frames are 802.3 (the device's receive decapsulation is Ethernet since level 7's parameters): the frame starts at
// the receive descriptor's end plus its L3 padding. An EAPOL frame (type 0x888e) goes to the owner's 802.1X path, every other
// frame to en0. Nothing here allocates, maps or sleeps.
#pragma once
#include <stdint.h>
#include "WifiCe.h"
#include "WifiHtt.h"
#include "WifiHw.h"
#include "WifiMhi.h"

namespace pianowifi {

constexpr uint32_t kDpTclEntries = 64, kDpTxCompEntries = 64, kDpReoEntries = 256, kDpReoExcEntries = 128,
                   kDpRelEntries = 256, kDpIdleEntries = 1024;
constexpr uint32_t kDpTxBuffers = 32, kDpTxBufferBytes = 2048;
constexpr uint32_t kDpReoErrQueueAddrZero = 0;   // the reorder unit's error 0: no queue descriptor for the frame's TID
constexpr uint32_t kDpLinkDescBytes = 128;
constexpr uint32_t kDpFrameMax = 1600;   // an 802.3 frame of en0 (1514 and a VLAN tag, rounded)

// piano-wifi-l8=N, level 8's switches (each the A/B of a default): bit 0 the receive buffers return to software ring 1 (the
// refill ring's manager; off: the firmware's own, as levels 6 and 7 have it), bit 1 the receive ring selection sent for both
// radio buffer rings, bit 2 the data path's rings programmed at all (off: level 8 does nothing), bit 3 EAPOL frames
// also to en0 (by default only to the 802.1X port), bit 4 the transmit side (off: nothing is sent, the receive side runs).
// Bit 5: the rings programmed at level 6's start, before the copy engine (off: at level 7's start). Boot 10c's reset at that
// placement was the ladder's stack overflowing (10d's mailbox), not the rings.
constexpr uint32_t kL8RbmSw1 = 1u << 0, kL8RxSelection = 1u << 1, kL8Rings = 1u << 2, kL8EapolToEn0 = 1u << 3, kL8Tx = 1u << 4,
                   kL8AtLevel6 = 1u << 5;
// Since boots 10f-a/b (2026-11-14): software ring 1 for the buffers, confirmed on the tablet (with the firmware's manager the
// firmware asserts as the first data frames come; 10f-b), and the rings at level 6's start so that a buffer released during
// the scan finds its ring: 0x37.
constexpr uint32_t kL8Default = kL8RbmSw1 | kL8RxSelection | kL8Rings | kL8Tx | kL8AtLevel6;

struct DpTxBuf {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t length = 0;
  bool busy = false;
};

// One released receive buffer as the release ring and the buffer itself describe it (boot 10f-c: 1891 releases after the
// keys, no frame delivered): the release's source and its push reason and error code, the descriptor's error bits, and two
// protocol facts of the frame (group addressed or not, its Ethernet type). Nothing private: no address, no payload.
struct DpRelRecord {
  uint32_t source = 0, rxdmaPush = 0, rxdmaError = 0, reoPush = 0, reoError = 0, info13 = 0, length = 0, etherType = 0;
  bool groupAddressed = false, descRead = false;
};
constexpr unsigned kDpRelRecords = 16;

struct DpStats {
  // receive
  uint32_t rxEntries = 0, rxFrames = 0, rxEapol = 0, rxBytes = 0, rxNotDone = 0, rxBadCookie = 0, rxErrors = 0, rxNullData = 0,
           rxMulti = 0, rxNotEthernet = 0, rxTooLong = 0, rxLinkDesc = 0, rxRecycled = 0, rxRecycleFull = 0;
  uint32_t excEntries = 0, relEntries = 0, relRecycled = 0, relOther = 0, relDelivered = 0;
  uint32_t relBySource[8] = {}, relRxdmaError[32] = {}, relReoError[32] = {}, relGroup = 0, relUnicast = 0;
  DpRelRecord rel[kDpRelRecords];   // the first kDpRelRecords releases
  uint32_t relRecorded = 0;
  uint32_t lastEapolLength = 0, lastDecap = 0, lastErrors = 0, lastPushReason = 0, lastErrorCode = 0;
  // transmit
  uint32_t txFrames = 0, txBytes = 0, txNoBuffer = 0, txRingFull = 0, txTooLong = 0, txNotReady = 0, txCompletions = 0,
           txAcked = 0, txNotAcked = 0, txFwReleased = 0, txOtherRelease = 0, txBadCookie = 0, txEapol = 0;
  uint32_t lastTxReason = 0, lastTxSource = 0;
};

struct Dp {
  CeRing tcl, txComp, reo, reoExc, rel3, idle;
  uint8_t *linkVa = nullptr;
  uint64_t linkBus = 0;
  uint32_t linkDescs = 0;
  DpTxBuf tx[kDpTxBuffers];
  HttRx *rx = nullptr;             // the refill ring the receive buffers go back into
  bool planned = false, programmed = false, txReady = false;
  uint32_t vdevId = 0, pdevId = 0, bank = 0, tclMetadata = 0, searchIndex = 0, cacheSet = 0, tid = 0;
  uint32_t writes = 0;
  uint32_t reoCookieCfg = 0, wbmCookieConvert = 0;   // read back at programming, for the log (WifiHw.h)
  uint32_t probeGen = 0, probeIdleMisc = 0;          // block 0's two reads
  uint32_t blocksDone = 0;                           // how many of dpProgramBlocks' blocks ran
  DpStats st;
};

namespace dpdetail {

inline void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}
inline uint32_t get32(const uint8_t *at)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[i]) << (8 * i);
  return v;
}
inline uint32_t get16(const uint8_t *at) { return uint32_t(at[0] | at[1] << 8); }

// The stores into the window (a descriptor, a buffer) are seen by the chip before the pointer write that publishes them.
inline void publishBarrier()
{
#if defined(__aarch64__)
  __asm__ volatile("dmb oshst" ::: "memory");
#else
  __atomic_thread_fence(__ATOMIC_RELEASE);
#endif
}

inline void write(Dp &dp, const ChipIo &io, uint32_t address, uint32_t value)
{
  ++dp.writes;
  io.write(io.ctx, address, value);
}

inline bool plan(CeRing &r, Arena &arena, uint32_t entries, uint32_t words, uint32_t r0, uint32_t r2, uint32_t ringId,
                 uint8_t *pointers, uint64_t pointersBus, uint32_t &index)
{
  uint64_t bus = 0;
  uint8_t *va = arenaAlloc(arena, entries * words * 4, &bus);
  if (!va) return false;
  r.va = va;
  r.bus = bus;
  r.entries = entries;
  r.words = words;
  r.r0 = r0;
  r.r2 = r2;
  r.ringId = ringId;
  r.ours = r.taken = 0;
  r.theirs = reinterpret_cast<volatile uint32_t *>(pointers + 4 * index);
  r.theirsBus = pointersBus + 4 * index;
  ++index;
  return true;
}

// One ring's registers: the copy engine's sequence (WifiCe.h programRing), with the idle link ring's two differences — no ring
// identifier check (misc bit 0) and no tail pointer address (the WBM keeps its own).
inline void program(Dp &dp, const ChipIo &io, CeRing &r, bool hostProduces, bool idleLink = false)
{
  const uint32_t sizeWords = r.entries * r.words;
  r.ours = r.taken = 0;
  if (r.theirs) *r.theirs = 0;
  write(dp, io, r.r0, uint32_t(r.bus & kRingAddrLowMask));
  write(dp, io, r.r0 + kRingBaseMsb,
        uint32_t((r.bus >> kRingAddrHiShift) & kRingBaseMsbAddrHi) | (sizeWords & kRingBaseMsbSizeMask) << kRingBaseMsbSizeShift);
  write(dp, io, r.r0 + kRingId, (r.words & kRingIdEntrySizeMask) | (hostProduces ? 0u : (r.ringId & 0xffu) << kRingIdRingIdShift));
  if (hostProduces) {
    write(dp, io, r.r0 + kSrcRingConsumerInt0, 0);
    write(dp, io, r.r0 + kSrcRingConsumerInt1, 0);
    if (!idleLink) {
      write(dp, io, r.r0 + kSrcRingTpAddrLo, uint32_t(r.theirsBus & kRingAddrLowMask));
      write(dp, io, r.r0 + kSrcRingTpAddrHi, uint32_t(r.theirsBus >> kRingAddrHiShift));
    }
  } else {
    write(dp, io, r.r0 + kDstRingProducerInt, 0);
    write(dp, io, r.r0 + kDstRingHpAddrLo, uint32_t(r.theirsBus & kRingAddrLowMask));
    write(dp, io, r.r0 + kDstRingHpAddrHi, uint32_t(r.theirsBus >> kRingAddrHiShift));
  }
  write(dp, io, r.r2, 0);
  write(dp, io, r.r2 + 4, 0);
  write(dp, io, r.r0 + kRingMisc,
        kRingMiscEnable | (hostProduces ? kRingMiscLoopCountDisable : 0u) | (idleLink ? kRingMiscNoRingId : 0u));
}

inline uint32_t slotOf(const CeRing &r, uint32_t pointer)
{
  const uint32_t size = r.entries * r.words;
  return size ? (pointer % size) / r.words : 0;
}

inline uint32_t load(const volatile uint32_t *at)
{
  if (!at) return 0;
  const uint32_t v = *at;
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  return v;
}

// The cookie of a buffer address info (bits 31:12 of its second word), and its address.
inline uint32_t cookieOf(const uint8_t *e) { return get32(e + 4) >> 12; }
inline uint64_t addrOf(const uint8_t *e) { return uint64_t(get32(e)) | uint64_t(get32(e + 4) & 0xffu) << 32; }

}  // namespace dpdetail

// Every ring, the link descriptors and the transmit buffers out of the window. False when it has no room.
inline bool dpPlan(Dp &dp, Arena &arena, HttRx *rx)
{
  using namespace dpdetail;
  renew(dp);
  dp.rx = rx;
  uint64_t pointersBus = 0;
  uint8_t *pointers = arenaAlloc(arena, 4 * 8, &pointersBus);
  if (!pointers) return false;
  uint32_t index = 0;
  if (!plan(dp.tcl, arena, kDpTclEntries, kDpTclEntryWords, kDpTcl1R0, kDpTcl1R2, 0, pointers, pointersBus, index) ||
      !plan(dp.txComp, arena, kDpTxCompEntries, kDpWbmEntryWords, kDpWbm2Sw0R0, kDpWbm2Sw0R2, kDpRingIdWbm2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.reo, arena, kDpReoEntries, kDpReoEntryWords, kDpReo2Sw1R0, kDpReo2Sw1R2, kDpRingIdReo2Sw1, pointers, pointersBus,
            index) ||
      !plan(dp.reoExc, arena, kDpReoExcEntries, kDpReoEntryWords, kDpReo2Sw0R0, kDpReo2Sw0R2, kDpRingIdReo2Sw0, pointers,
            pointersBus, index) ||
      !plan(dp.rel3, arena, kDpRelEntries, kDpWbmEntryWords, kDpWbm2Sw0R0 + 3 * kDpWbm2SwR0Stride,
            kDpWbm2Sw0R2 + 3 * kDpWbm2SwR2Stride, kDpRingIdWbm2Sw0 + 3, pointers, pointersBus, index) ||
      !plan(dp.idle, arena, kDpIdleEntries, kDpIdleEntryWords, kDpIdleLinkR0, kDpIdleLinkR2, 0, pointers, pointersBus, index))
    return false;
  dp.linkDescs = kDpIdleEntries - 1;
  dp.linkVa = arenaAlloc(arena, dp.linkDescs * kDpLinkDescBytes, &dp.linkBus);   // 128-byte aligned (the arena's rule)
  if (!dp.linkVa) return false;
  for (DpTxBuf &b : dp.tx) {
    b.va = arenaAlloc(arena, kDpTxBufferBytes, &b.bus);
    if (!b.va) return false;
  }
  dp.planned = true;
  return true;
}

// The register blocks dpProgram writes, in order (boot 10c, 2026-11-14, reset the tablet right after the firmware's mode with
// these programmed at level 6's start and no line of it printed: each block is now named, with its addresses, before its first
// access, and the owner may stop after any of them). Block 0 only reads.
enum DpBlock : uint32_t {
  kDpBlockProbe = 0,    // reads: the reorder unit's general enable, the idle link ring's misc
  kDpBlockTcl = 1,      // TCL data ring 1
  kDpBlockTxComp = 2,   // WBM2SW0, its completions
  kDpBlockReo = 3,      // REO2SW1
  kDpBlockReoExc = 4,   // REO2SW0
  kDpBlockRel = 5,      // WBM2SW3
  kDpBlockIdle = 6,     // the WBM idle link ring, its 1023 entries and its head
  kDpBlockReoSetup = 7, // the reorder unit's set-up and the cookie conversion's enables (read)
  kDpBlocks = 8
};

inline const char *dpBlockName(uint32_t block)
{
  switch (block) {
  case kDpBlockProbe: return "two reads of the data path's units (REO1_GEN_ENABLE, the WBM idle link ring's misc)";
  case kDpBlockTcl: return "TCL data ring 1 (transmit)";
  case kDpBlockTxComp: return "WBM2SW0 (transmit completions)";
  case kDpBlockReo: return "REO2SW1 (received MSDUs)";
  case kDpBlockReoExc: return "REO2SW0 (the reorder unit's exceptions)";
  case kDpBlockRel: return "WBM2SW3 (the receive error release ring)";
  case kDpBlockIdle: return "the WBM idle link ring (its entries and head)";
  case kDpBlockReoSetup: return "the reorder unit's set-up (general enable, misc, aging, the hash's destinations; the cookie enables read)";
  default: return "?";
  }
}

// A block's addresses: its R0 range and its R2 pair, or for the set-up blocks the lowest and highest register they touch.
struct DpBlockRange {
  uint32_t first = 0, last = 0, r2 = 0;
};
inline DpBlockRange dpBlockRange(const Dp &dp, uint32_t block)
{
  auto ring = [](const CeRing &r, bool hostProduces) {
    DpBlockRange g;
    g.first = r.r0;
    g.last = r.r0 + (hostProduces ? kSrcRingConsumerInt1 : kDstRingProducerInt);
    g.r2 = r.r2;
    return g;
  };
  switch (block) {
  case kDpBlockProbe: return DpBlockRange{kDpReoGenEnable, kDpIdleLinkR0 + kRingMisc, 0};
  case kDpBlockTcl: return ring(dp.tcl, true);
  case kDpBlockTxComp: return ring(dp.txComp, false);
  case kDpBlockReo: return ring(dp.reo, false);
  case kDpBlockReoExc: return ring(dp.reoExc, false);
  case kDpBlockRel: return ring(dp.rel3, false);
  case kDpBlockIdle: return ring(dp.idle, true);
  case kDpBlockReoSetup: return DpBlockRange{kDpReoGenEnable, kDpReoMiscCtrl, 0};
  default: return DpBlockRange{};
  }
}

// The rings' registers, the idle link ring filled with every link descriptor, and the reorder unit's set-up, block by block.
// `trace(ctx, block)` runs before each block's first access (the owner logs it and lets the console take the line); blocks
// above `lastBlock` are left out, and then the data path is not "programmed" (nothing polls a half-made set of rings).
template <class Trace>
inline void dpProgramBlocks(Dp &dp, const ChipIo &io, uint32_t lastBlock, Trace trace)
{
  using namespace dpdetail;
  if (!dp.planned) return;
  for (uint32_t block = 0; block < kDpBlocks; ++block) {
    if (block > lastBlock) return;
    trace(block);
    switch (block) {
    case kDpBlockProbe:
      dp.probeGen = io.read(io.ctx, kDpReoGenEnable);
      dp.probeIdleMisc = io.read(io.ctx, kDpIdleLinkR0 + kRingMisc);
      break;
    case kDpBlockTcl: program(dp, io, dp.tcl, true); break;
    case kDpBlockTxComp: program(dp, io, dp.txComp, false); break;
    case kDpBlockReo: program(dp, io, dp.reo, false); break;
    case kDpBlockReoExc: program(dp, io, dp.reoExc, false); break;
    case kDpBlockRel: program(dp, io, dp.rel3, false); break;
    case kDpBlockIdle: {
      program(dp, io, dp.idle, true, true);
      // each link descriptor one entry of the idle ring (its address, manager "WBM idle descriptor list", cookie = its index)
      for (uint32_t i = 0; i < dp.linkDescs; ++i) {
        uint8_t *e = dp.idle.va + i * dp.idle.words * 4;
        const uint64_t bus = dp.linkBus + uint64_t(i) * kDpLinkDescBytes;
        put32(e, uint32_t(bus & 0xffffffffu));
        put32(e + 4, uint32_t((bus >> 32) & 0xffu) | kDpRbmIdleDescDev0 << 8 | (i & 0xfffffu) << 12);
      }
      dp.idle.ours = dp.linkDescs;
      publishBarrier();
      write(dp, io, dp.idle.r2, dp.idle.ours * dp.idle.words);
      break;
    }
    case kDpBlockReoSetup: {
      // aging on, fragments and BARs to the exception ring, the aging thresholds, every hash entry to REO2SW1
      const uint32_t gen = io.read(io.ctx, kDpReoGenEnable);
      write(dp, io, kDpReoGenEnable, gen | kDpReoGenAgingList | kDpReoGenAgingFlush);
      const uint32_t misc = io.read(io.ctx, kDpReoMiscCtrl) & ~(kDpReoMiscFragMask | kDpReoMiscBarMask);
      write(dp, io, kDpReoMiscCtrl, misc | kDpRingIdReo2Sw0 << 17 | kDpRingIdReo2Sw0 << 21);
      write(dp, io, kDpReoAgingIx0 + 0, kDpReoAgingBeUs);
      write(dp, io, kDpReoAgingIx0 + 4, kDpReoAgingBeUs);
      write(dp, io, kDpReoAgingIx0 + 8, kDpReoAgingBeUs);
      write(dp, io, kDpReoAgingIx0 + 12, kDpReoAgingVoUs);
      write(dp, io, kDpReoDestIx2, kDpReoHashAllSw1);
      write(dp, io, kDpReoDestIx3, kDpReoHashAllSw1);
      dp.reoCookieCfg = io.read(io.ctx, kDpReoSwCookieCfg1);
      dp.wbmCookieConvert = io.read(io.ctx, kDpWbmCookieConvert);
      break;
    }
    default: break;
    }
    dp.blocksDone = block + 1;
  }
  dp.programmed = true;
}

inline void dpProgram(Dp &dp, const ChipIo &io)
{
  dpProgramBlocks(dp, io, kDpBlocks - 1, [](uint32_t) {});
}

// True when the hardware would rewrite the entries' cookies (something else set conversion up): the log says so.
inline bool dpCookieConversionOn(const Dp &dp)
{
  return (dp.reoCookieCfg & kDpReoCookieEnables) || (dp.wbmCookieConvert & kDpWbmCookieEnables);
}

// The transmit side for a joined station: the bank's configuration (bank 0), the TCL metadata naming the device and its radio,
// and the access point's search index (the peer map's hardware peer and hash, which only the second and third peer-map forms
// carry; the first gives none, and then they are 0, as this chip's host leaves them).
inline void dpTxSetup(Dp &dp, const ChipIo &io, uint32_t vdevId, uint32_t pdevId, uint32_t searchIndex, uint32_t cacheSet)
{
  using namespace dpdetail;
  dp.vdevId = vdevId;
  dp.pdevId = pdevId;
  dp.bank = 0;
  dp.tclMetadata = kDpTclMetaVdevType | (vdevId & 0xffu) << kDpTclMetaVdevShift | (pdevId & 0x3u) << kDpTclMetaPdevShift;
  dp.searchIndex = searchIndex & 0xfffffu;
  dp.cacheSet = cacheSet & 0xfu;
  write(dp, io, kDpTclBankConfig + 4 * dp.bank, kDpBankStation);
  dp.txReady = dp.programmed;
}

// The same from the access point's peer map (null: no map, index 0).
inline void dpTxSetupPeer(Dp &dp, const ChipIo &io, uint32_t vdevId, uint32_t pdevId, const HttPeerMap *peer)
{
  const bool search = peer && peer->hasSearch;
  dpTxSetup(dp, io, vdevId, pdevId, search ? peer->hwPeerId : 0, search ? peer->astHash : 0);
}

inline void dpTxStop(Dp &dp) { dp.txReady = false; }

// The receive DMA's ring selection for radio buffer ring `radio` (0, 1): what this chip's host sends for each of them — data
// frames (unicast, multicast, null data) and BARs to the host, the descriptor's TLVs (MPDU start, MSDU end, the packet) at the
// offsets QCC2072's descriptor has them. Returns its length.
inline uint32_t httBuildRxSelection(uint8_t *at, uint32_t capacity, uint32_t radio)
{
  using namespace dpdetail;
  const uint32_t bytes = kHttRxSelectionWords * 4;
  if (!at || capacity < bytes) return 0;
  for (uint32_t i = 0; i < bytes; ++i) at[i] = 0;
  put32(at + 0, kHttMsgRxRingSelectionCfg | ((radio + 1) & 0xffu) << 8 | kHttRingRxdmaHostBuf << 16 | kHttRxSelOffsetValid |
                    kHttRxSelRxMon);
  put32(at + 4, kRxBufferBytes & 0xffffu);
  put32(at + 4 * 4, kHttRxSelCtrlBar);
  put32(at + 4 * 5, kHttRxSelDataMcast | kHttRxSelDataUcast | kHttRxSelDataNull);
  put32(at + 4 * 6, kHttRxSelTlvs);
  put32(at + 4 * 7, (kRxDescBytes & 0xffffu) | (kRxDescPktHdr & 0xffffu) << 16);
  put32(at + 4 * 8, (kRxDescMpduStartTag & 0xffffu) << 16);
  put32(at + 4 * 9, kRxDescMsduEndTag & 0xffffu);
  return bytes;
}

// An 802.3 frame out: a transmit buffer, the descriptor, the TCL ring's head. False when the station is not up, the frame does
// not fit, every buffer is in flight or the ring is full (the caller keeps the frame for a later turn or drops it).
inline bool dpSend(Dp &dp, const ChipIo &io, const uint8_t *frame, uint32_t length)
{
  using namespace dpdetail;
  if (!dp.txReady) {
    ++dp.st.txNotReady;
    return false;
  }
  if (!frame || length < 14 || length > kDpTxBufferBytes) {
    ++dp.st.txTooLong;
    return false;
  }
  int buffer = -1;
  for (uint32_t i = 0; i < kDpTxBuffers; ++i)
    if (!dp.tx[i].busy) {
      buffer = int(i);
      break;
    }
  if (buffer < 0) {
    ++dp.st.txNoBuffer;
    return false;
  }
  CeRing &r = dp.tcl;
  const uint32_t theirs = slotOf(r, load(r.theirs));
  if ((r.ours + 1) % r.entries == theirs) {
    ++dp.st.txRingFull;
    return false;
  }
  DpTxBuf &b = dp.tx[buffer];
  for (uint32_t i = 0; i < length; ++i) b.va[i] = frame[i];
  b.length = length;
  b.busy = true;
  uint8_t *e = r.va + r.ours * r.words * 4;
  put32(e + 0, uint32_t(b.bus & 0xffffffffu));
  put32(e + 4, uint32_t((b.bus >> 32) & 0xffu) | kDpRbmSw0 << 8 | (uint32_t(buffer) & 0xfffffu) << 12);
  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift);                          // a buffer, bank 0
  put32(e + 12, (dp.tclMetadata & 0xffffu) << kDpTclCmdNumShift);
  put32(e + 16, length & 0xffffu);                                              // no offset, not to the firmware
  put32(e + 20, kDpTclTidOverwrite | (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);
  put32(e + 24, dp.searchIndex | dp.cacheSet << kDpTclCacheSetShift);
  put32(e + 28, 0);
  r.ours = (r.ours + 1) % r.entries;
  publishBarrier();
  write(dp, io, r.r2, r.ours * r.words);
  ++dp.st.txFrames;
  dp.st.txBytes += length;
  if (length >= 14 && frame[12] == 0x88 && frame[13] == 0x8e) ++dp.st.txEapol;
  return true;
}

// What a received frame is to the owner: 0 an 802.3 frame for en0, 1 an EAPOL frame (for the 802.1X path).
enum DpRxKind : uint32_t { kDpRxEthernet = 0, kDpRxEapol = 1 };

namespace dpdetail {
// One received MSDU out of its buffer: the descriptor's checks (done, no error, not null data, one buffer, Ethernet II, a
// length that fits), then deliver(kind, frame, length). `first`/`last`/`continuation` are the MSDU's place in its MPDU, as the
// ring entry (or, for a released buffer, the descriptor) gives it. Returns true when the frame was delivered.
template <class Deliver>
inline bool deliverBuffer(Dp &dp, const uint8_t *va, bool first, bool last, bool continuation, Deliver &deliver)
{
  const uint32_t info14 = get32(va + kRxDescInfo14), info13 = get32(va + kRxDescInfo13);
  const uint32_t info5 = get16(va + kRxDescInfo5), info11 = get32(va + kRxDescInfo11);
  const uint32_t pad = (info5 >> kRxDescL3PadShift) & kRxDescL3PadMask;
  const uint32_t length = get32(va + kRxDescInfo10) & kRxDescMsduLenMask;
  const uint32_t decap = (info11 >> kRxDescDecapShift) & kRxDescDecapMask;
  dp.st.lastDecap = decap;
  if (!(info14 & kRxDescMsduDone)) {
    ++dp.st.rxNotDone;
  } else if (info13 & kRxDescErrors) {
    ++dp.st.rxErrors;
    dp.st.lastErrors = info13 & kRxDescErrors;
  } else if (info13 & kRxDescNullData) {
    ++dp.st.rxNullData;
  } else if (!first || !last || continuation) {
    ++dp.st.rxMulti;   // an MSDU over more than one buffer: not at this level (2 KiB buffers carry 1500-byte frames)
  } else if (decap != kRxDecapEthernet) {
    ++dp.st.rxNotEthernet;
  } else if (length < 14 || kRxDescBytes + pad + length > kRxBufferBytes) {
    ++dp.st.rxTooLong;
  } else {
    const uint8_t *frame = va + kRxDescBytes + pad;
    const bool eapol = frame[12] == 0x88 && frame[13] == 0x8e;
    ++dp.st.rxFrames;
    dp.st.rxBytes += length;
    if (eapol) {
      ++dp.st.rxEapol;
      dp.st.lastEapolLength = length;
    }
    deliver(eapol ? kDpRxEapol : kDpRxEthernet, frame, length);
    return true;
  }
  return false;
}
}  // namespace dpdetail

// One turn: the transmit completions, the received MSDUs (each delivered and its buffer posted again), the release rings'
// buffers posted again, the exception ring passed over. `deliver(kind, frame, length)` gets each frame; the frame lives in the
// receive buffer only until deliver returns. Returns how many entries were seen.
template <class Deliver>
inline uint32_t dpPoll(Dp &dp, const ChipIo &io, Deliver deliver)
{
  using namespace dpdetail;
  uint32_t seen = 0;
  if (!dp.programmed) return 0;
  // ---- transmit completions
  {
    CeRing &r = dp.txComp;
    const uint32_t head = slotOf(r, load(r.theirs));
    bool moved = false;
    while (r.ours != head) {
      const uint8_t *e = r.va + r.ours * r.words * 4;
      const uint32_t cookie = cookieOf(e), info0 = get32(e + 8);
      const uint32_t source = info0 & kDpRelSrcMask, reason = (info0 >> kDpTqmReasonShift) & kDpTqmReasonMask;
      ++dp.st.txCompletions;
      dp.st.lastTxSource = source;
      dp.st.lastTxReason = reason;
      if (source == kDpRelSrcTqm) {
        if (reason == 0) ++dp.st.txAcked;
        else ++dp.st.txNotAcked;
      } else if (source == kDpRelSrcFw) {
        ++dp.st.txFwReleased;
      } else {
        ++dp.st.txOtherRelease;
      }
      if (cookie < kDpTxBuffers && dp.tx[cookie].busy && addrOf(e) == dp.tx[cookie].bus) dp.tx[cookie].busy = false;
      else ++dp.st.txBadCookie;
      r.ours = (r.ours + 1) % r.entries;
      moved = true;
      ++seen;
    }
    if (moved) write(dp, io, r.r2 + 4, r.ours * r.words);
  }
  // ---- received MSDUs
  {
    CeRing &r = dp.reo;
    const uint32_t head = slotOf(r, load(r.theirs));
    bool moved = false;
    while (r.ours != head) {
      const uint8_t *e = r.va + r.ours * r.words * 4;
      r.ours = (r.ours + 1) % r.entries;
      moved = true;
      ++seen;
      ++dp.st.rxEntries;
      const uint32_t info0 = get32(e + 28), msdu = get32(e + 16);
      if (info0 & kDpReoBufTypeLinkDesc) {   // a link descriptor on the data ring: not ours to read at this level
        ++dp.st.rxLinkDesc;
        continue;
      }
      const uint32_t cookie = cookieOf(e);
      HttRx *rx = dp.rx;
      if (!rx || cookie + 1 >= kRxRefillEntries || addrOf(e) != rx->refillBus[cookie]) {
        ++dp.st.rxBadCookie;
        continue;
      }
      const uint8_t *va = rx->refillVa[cookie];
      if (va)
        deliverBuffer(dp, va, (msdu & kDpMsduFirst) != 0, (msdu & kDpMsduLast) != 0, (msdu & kDpMsduContinuation) != 0, deliver);
      // the buffer goes back into the refill ring whatever its frame was
      if (httRefillPost(*rx, cookie)) ++dp.st.rxRecycled;
      else ++dp.st.rxRecycleFull;
    }
    if (moved) {
      publishBarrier();
      write(dp, io, r.r2 + 4, r.ours * r.words);
    }
  }
  // ---- the reorder unit's exceptions: counted and passed over (their entries name link descriptors, level 8's next piece)
  {
    CeRing &r = dp.reoExc;
    const uint32_t head = slotOf(r, load(r.theirs));
    bool moved = false;
    while (r.ours != head) {
      const uint8_t *e = r.va + r.ours * r.words * 4;
      const uint32_t info0 = get32(e + 28);
      dp.st.lastPushReason = (info0 >> kDpReoPushShift) & 0x3u;
      dp.st.lastErrorCode = (info0 >> kDpReoErrShift) & 0x1fu;
      r.ours = (r.ours + 1) % r.entries;
      moved = true;
      ++seen;
      ++dp.st.excEntries;
    }
    if (moved) write(dp, io, r.r2 + 4, r.ours * r.words);
  }
  // ---- released receive buffers (ring 3, this chip's host's receive error ring)
  {
    CeRing &r = dp.rel3;
    const uint32_t head = slotOf(r, load(r.theirs));
    bool moved = false;
    while (r.ours != head) {
      const uint8_t *e = r.va + r.ours * r.words * 4;
      const uint32_t cookie = cookieOf(e);
      r.ours = (r.ours + 1) % r.entries;
      moved = true;
      ++seen;
      ++dp.st.relEntries;
      HttRx *rx = dp.rx;
      const bool ours = rx && cookie + 1 < kRxRefillEntries && addrOf(e) == rx->refillBus[cookie];
      // why it was released: info0 (word 2) the source (2:0), the receive DMA's push reason (18:17) and error (23:19), the
      // reorder unit's push reason (25:24) and error (30:26)
      const uint32_t info0 = get32(e + 8);
      DpRelRecord rec;
      rec.source = info0 & kDpRelSrcMask;
      rec.rxdmaPush = (info0 >> 17) & 0x3u;
      rec.rxdmaError = (info0 >> 19) & 0x1fu;
      rec.reoPush = (info0 >> 24) & 0x3u;
      rec.reoError = (info0 >> 26) & 0x1fu;
      ++dp.st.relBySource[rec.source];
      if (rec.source == kDpRelSrcRxdma) ++dp.st.relRxdmaError[rec.rxdmaError];
      if (rec.source == kDpRelSrcReo) ++dp.st.relReoError[rec.reoError];
      if (ours && rx->refillVa[cookie]) {
        const uint8_t *va = rx->refillVa[cookie];
        rec.descRead = true;
        rec.info13 = get32(va + kRxDescInfo13);
        rec.length = get32(va + kRxDescInfo10) & kRxDescMsduLenMask;
        const uint32_t pad = (get16(va + kRxDescInfo5) >> kRxDescL3PadShift) & kRxDescL3PadMask;
        const uint8_t *frame = va + kRxDescBytes + pad;
        if (rec.length >= 14 && kRxDescBytes + pad + 14 <= kRxBufferBytes) {
          rec.groupAddressed = (frame[0] & 1) != 0;
          rec.etherType = uint32_t(frame[12]) << 8 | frame[13];
        }
        if (rec.groupAddressed || (rec.info13 & kRxDescMcbc)) ++dp.st.relGroup;
        else ++dp.st.relUnicast;
      }
      if (dp.st.relRecorded < kDpRelRecords) dp.st.rel[dp.st.relRecorded++] = rec;
      // The reorder unit releases a frame for which it has no queue (push reason 0, error 0: the queue descriptor's address is
      // zero) — this chip's group-addressed frames when they are not routed to the non-QoS queue (boot 10g: every ARP and
      // IPv4 broadcast of the access point came this way, decrypted, with no error bit). This chip's host passes such a frame
      // up after the same checks as any other; so does this one.
      if (ours && rec.source == kDpRelSrcReo && rec.reoPush == 0 && rec.reoError == kDpReoErrQueueAddrZero && rx->refillVa[cookie]) {
        const uint8_t *va = rx->refillVa[cookie];
        const uint32_t info5 = get16(va + kRxDescInfo5);
        if (deliverBuffer(dp, va, (info5 & kRxDescFirstMsdu) != 0, (info5 & kRxDescLastMsdu) != 0, false, deliver))
          ++dp.st.relDelivered;
      }
      if (ours && httRefillPost(*rx, cookie))
        ++dp.st.relRecycled;
      else
        ++dp.st.relOther;
    }
    if (moved) {
      publishBarrier();
      write(dp, io, r.r2 + 4, r.ours * r.words);
    }
  }
  return seen;
}

}  // namespace pianowifi
