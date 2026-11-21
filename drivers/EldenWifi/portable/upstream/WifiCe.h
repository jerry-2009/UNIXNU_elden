// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 6, the pipe: the chip's copy engine as a portable piece the owner steps (host tests: tests/wmi_host.cpp against
// a copy-engine model). New code for this repository; the registers, the descriptors and the ring discipline are hardware facts
// of WifiHw.h, read from the Ubuntu kernel of docs/drivers/wifi.md section 3 for the wire shapes only — no code, comment or table
// of it is here.
//
// A pipe is three rings in the DMA window level 4 holds, and the pipes are the ones level 5 described to the firmware
// (WifiHw.h kCePipes, the firmware's side; kCeHostPipes, ours):
//   the source ring        the host writes a descriptor naming a buffer to send; the chip reads the buffer and advances its own
//                          pointer, which it writes into host memory (so nothing has to be read back through the window);
//   the destination ring   the host writes a descriptor naming an empty buffer; the chip fills it. It is a producer ring of the
//                          host's just like the source ring;
//   the destination-status ring  the chip writes one descriptor per buffer it filled, with the length — the only ring the chip
//                          produces into, so the host's pointer is the one it advances after reading.
// Every pointer the host owns lives in the chip's register space and is written through the BAR0 window (ChipIo); every pointer
// the chip owns lives in the window, in a block of its own, and is read with a volatile load.
//
// Nothing here maps memory, allocates or sleeps: the arena is the owner's and every wait is the owner's bounded poll. No
// interrupt is used (no MSI is programmed and no interrupt threshold is set): the owner polls, as levels 4 and 5 do.
#pragma once
#include <stdint.h>
#include "WifiHw.h"
#include "WifiMhi.h"

namespace pianowifi {

// The chip's registers above the window's start, reached through BAR0's window register (the owner's chipRead / chipWrite).
struct ChipIo {
  void *ctx = nullptr;
  uint32_t (*read)(void *ctx, uint32_t address) = nullptr;
  void (*write)(void *ctx, uint32_t address, uint32_t value) = nullptr;
};

enum CeEvent : uint32_t { kCeNothing = 0, kCeReceived, kCeSent };

struct CeRing {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t entries = 0, words = 0;        // descriptors in the ring, 32-bit words per descriptor
  uint32_t r0 = 0, r2 = 0;                // the chip's register blocks of this ring
  uint32_t ringId = 0;
  uint32_t ours = 0;                      // our own pointer: the next slot we write (producer) or read (the status ring)
  uint32_t taken = 0;                     // producer rings: the next slot whose completion we have not taken yet
  volatile uint32_t *theirs = nullptr;    // where the chip writes its own pointer (a byte offset into the ring)
  uint64_t theirsBus = 0;
};

struct CeBuffer {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t bytes = 0, length = 0;
  bool busy = false;
};

constexpr unsigned kCeRxBuffersMax = 64;          // the largest destination ring of kCeHostPipes, less the elements left free

struct CePipe {
  uint8_t pipe = 0;
  bool hasSrc = false, hasDst = false;
  CeRing src, dst, status;
  CeBuffer rx[kCeRxBuffersMax];
  uint32_t rxCount = 0;
  uint32_t slot[kCeRxBuffersMax + kCeDstKeepFree] = {};   // destination ring slot -> which buffer sits in it
  uint32_t txSlot[kCeSendBuffers * 4] = {};              // source ring slot -> which send buffer sits in it
};

struct Ce {
  CePipe pipes[kCeHostPipeCount];
  CeBuffer tx[kCeSendBuffers];
  uint32_t pointerCount = 0;
  // counters and the last thing seen, for the log
  uint32_t sent = 0, received = 0, completions = 0, posted = 0, refused = 0, dropped = 0, bytesIn = 0, bytesOut = 0;
  uint32_t writes = 0;
  const char *error = nullptr;
};

namespace cedetail {

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
// The chip's own pointer, and then the descriptors it points past: the two loads must not be reordered, or a descriptor could
// be read before the write that filled it (this firmware's own host puts a read barrier in exactly this place). An acquire
// fence is a `dmb ishld` on this processor and costs nothing on the host the tests run on.
inline uint32_t load(const volatile uint32_t *at)
{
  if (!at) return 0;
  const uint32_t value = *at;
  __atomic_thread_fence(__ATOMIC_ACQUIRE);
  return value;
}

inline void chipWrite(Ce &ce, const ChipIo &io, uint32_t address, uint32_t value)
{
  ++ce.writes;
  io.write(io.ctx, address, value);
}

// One ring of a pipe, out of the arena: its descriptors and the word the chip writes its pointer into.
inline bool planRing(CeRing &r, Arena &arena, uint32_t entries, uint32_t words, uint32_t r0, uint32_t r2, uint32_t ringId,
                     uint8_t *pointers, uint64_t pointersBus, uint32_t &pointerIndex)
{
  const uint32_t bytes = entries * words * 4;
  if (!entries || (entries & (entries - 1)) || entries * words > kCeRingSizeMaxWords) return false;
  uint64_t bus = 0;
  uint8_t *va = arenaAlloc(arena, bytes, &bus);
  if (!va) return false;
  r.va = va;
  r.bus = bus;
  r.entries = entries;
  r.words = words;
  r.r0 = r0;
  r.r2 = r2;
  r.ringId = ringId;
  r.ours = 0;
  r.taken = 0;
  r.theirs = reinterpret_cast<volatile uint32_t *>(pointers + 4 * pointerIndex);
  r.theirsBus = pointersBus + 4 * pointerIndex;
  ++pointerIndex;
  return true;
}

// The registers of one ring. A ring the host produces into (the source and the destination rings) tells the chip where to write
// its tail pointer; a ring the chip produces into (the destination-status ring) tells it where to write its head pointer.
inline void programRing(Ce &ce, const ChipIo &io, CeRing &r, bool hostProduces)
{
  const uint32_t sizeWords = r.entries * r.words;
  // The host's two indexes and the word the chip writes its own pointer into all start at zero, so that a ring programmed
  // again (after a teardown, say) cannot leave the two sides disagreeing about where they are.
  r.ours = 0;
  r.taken = 0;
  if (r.theirs) *r.theirs = 0;
  chipWrite(ce, io, r.r0, uint32_t(r.bus & kRingAddrLowMask));
  chipWrite(ce, io, r.r0 + kRingBaseMsb,
            uint32_t((r.bus >> kRingAddrHiShift) & kRingBaseMsbAddrHi) | (sizeWords & kRingBaseMsbSizeMask) << kRingBaseMsbSizeShift);
  chipWrite(ce, io, r.r0 + kRingId,
            (r.words & kRingIdEntrySizeMask) | (hostProduces ? 0u : (r.ringId & 0xffu) << kRingIdRingIdShift));
  // No interrupt of any kind: no MSI address, no timer and no batch threshold (the owner polls).
  if (hostProduces) {
    chipWrite(ce, io, r.r0 + kSrcRingConsumerInt0, 0);
    chipWrite(ce, io, r.r0 + kSrcRingConsumerInt1, 0);
    chipWrite(ce, io, r.r0 + kSrcRingTpAddrLo, uint32_t(r.theirsBus & kRingAddrLowMask));
    chipWrite(ce, io, r.r0 + kSrcRingTpAddrHi, uint32_t(r.theirsBus >> kRingAddrHiShift));
  } else {
    chipWrite(ce, io, r.r0 + kDstRingProducerInt, 0);
    chipWrite(ce, io, r.r0 + kDstRingHpAddrLo, uint32_t(r.theirsBus & kRingAddrLowMask));
    chipWrite(ce, io, r.r0 + kDstRingHpAddrHi, uint32_t(r.theirsBus >> kRingAddrHiShift));
  }
  chipWrite(ce, io, r.r2, 0);
  chipWrite(ce, io, r.r2 + 4, 0);
  chipWrite(ce, io, r.r0 + kRingMisc, kRingMiscEnable | (hostProduces ? kRingMiscLoopCountDisable : 0u));
}

// Both pointers of a ring count 32-bit words, not bytes and not descriptors (the ring's size register counts words too): the
// slot an index stands for begins at `slot * words` words into the ring. These two turn one into the other.
inline uint32_t pointerOf(const CeRing &r, uint32_t slot) { return slot * r.words; }
inline uint32_t slotOf(const CeRing &r, uint32_t pointer)
{
  const uint32_t size = r.entries * r.words;
  return size ? (pointer % size) / r.words : 0;
}

// How many descriptors the host may still write into a ring it produces into (one element always stays free, as the chip tells
// "empty" from "full" by the two pointers alone).
inline uint32_t freeEntries(const CeRing &r)
{
  if (!r.entries) return 0;
  const uint32_t theirs = slotOf(r, load(r.theirs));
  const uint32_t used = (r.ours + r.entries - theirs) % r.entries;
  return r.entries - used - 1;
}

}  // namespace cedetail

// The rings, the buffers and the block of pointers out of the arena. False when the arena has no room for all of it.
inline bool cePlan(Ce &ce, Arena &arena, uint32_t pipeMask = kCePipeMaskLevel6)
{
  using namespace cedetail;
  uint32_t rings = 0;
  for (const CeHostPipe &p : kCeHostPipes)
    if (pipeMask & (1u << p.pipe)) rings += (p.srcEntries ? 1u : 0u) + (p.dstEntries ? 2u : 0u);
  uint64_t pointersBus = 0;
  uint8_t *pointers = arenaAlloc(arena, 4 * rings, &pointersBus);   // the chip's own pointers, in one block of its own
  if (!pointers) return false;
  ce.pointerCount = rings;
  uint32_t pointerIndex = 0;
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    const CeHostPipe &want = kCeHostPipes[i];
    CePipe &pipe = ce.pipes[i];
    pipe.pipe = want.pipe;
    if (!(pipeMask & (1u << want.pipe))) continue;   // a pipe this level does not use: no ring, no register written
    const uint32_t srcUnit = kUnitCe0Src + want.pipe * kCeUnitStride;
    const uint32_t dstUnit = kUnitCe0Dst + want.pipe * kCeUnitStride;
    if (want.srcEntries) {
      if (want.srcEntries > sizeof pipe.txSlot / sizeof pipe.txSlot[0]) return false;
      if (!planRing(pipe.src, arena, want.srcEntries, kCeSrcDescWords, srcUnit, srcUnit + kCeR2Hp,
                    kRingIdCe0Src + want.pipe, pointers, pointersBus, pointerIndex))
        return false;
      pipe.hasSrc = true;
    }
    if (want.dstEntries) {
      if (want.dstEntries > kCeRxBuffersMax + kCeDstKeepFree) return false;
      if (!planRing(pipe.dst, arena, want.dstEntries, kCeDstDescWords, dstUnit, dstUnit + kCeR2Hp, kRingIdCe0Dst + want.pipe,
                    pointers, pointersBus, pointerIndex))
        return false;
      if (!planRing(pipe.status, arena, want.dstEntries, kCeStatusDescWords, dstUnit + kCeStatusRingBase,
                    dstUnit + kCeStatusR2Hp, kRingIdCe0DstStatus + want.pipe, pointers, pointersBus, pointerIndex))
        return false;
      pipe.hasDst = true;
      pipe.rxCount = want.dstEntries - kCeDstKeepFree;
      for (uint32_t b = 0; b < pipe.rxCount; ++b) {
        pipe.rx[b].va = arenaAlloc(arena, want.bufferBytes, &pipe.rx[b].bus);
        if (!pipe.rx[b].va) return false;
        pipe.rx[b].bytes = want.bufferBytes;
      }
    }
  }
  for (CeBuffer &b : ce.tx) {
    b.va = arenaAlloc(arena, kCeSendBufferBytes, &b.bus);
    if (!b.va) return false;
    b.bytes = kCeSendBufferBytes;
  }
  return true;
}

// The rings' registers, through the window. The destination ring also carries the largest buffer the chip may fill.
inline void ceProgram(Ce &ce, const ChipIo &io)
{
  using namespace cedetail;
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    CePipe &pipe = ce.pipes[i];
    if (pipe.hasSrc) programRing(ce, io, pipe.src, true);
    if (!pipe.hasDst) continue;
    programRing(ce, io, pipe.dst, true);
    const uint32_t dstUnit = kUnitCe0Dst + pipe.pipe * kCeUnitStride;
    const uint32_t ctrl = (io.read(io.ctx, dstUnit + kCeDstRingCtrl) & ~kCeDstRingCtrlMaxLen) |
                          (kCeHostPipes[i].bufferBytes & kCeDstRingCtrlMaxLen);
    chipWrite(ce, io, dstUnit + kCeDstRingCtrl, ctrl);
    programRing(ce, io, pipe.status, false);
  }
}

// Every free buffer of a pipe into its destination ring, then one pointer write. Returns how many were posted.
inline unsigned cePostRx(Ce &ce, const ChipIo &io, unsigned index)
{
  using namespace cedetail;
  if (index >= kCeHostPipeCount) return 0;
  CePipe &pipe = ce.pipes[index];
  if (!pipe.hasDst) return 0;
  unsigned posted = 0;
  for (uint32_t b = 0; b < pipe.rxCount; ++b) {
    CeBuffer &buffer = pipe.rx[b];
    if (buffer.busy || !buffer.va) continue;
    if (!freeEntries(pipe.dst)) break;
    uint8_t *desc = pipe.dst.va + pipe.dst.ours * pipe.dst.words * 4;
    put32(desc, uint32_t(buffer.bus & kRingAddrLowMask));
    put32(desc + 4, uint32_t((buffer.bus >> kRingAddrHiShift) & kCeDescAddrHiMask) |
                        (pipe.dst.ringId & 0xffu) << kCeDescRingIdShift);
    pipe.slot[pipe.dst.ours] = b;
    buffer.busy = true;
    buffer.length = 0;
    pipe.dst.ours = (pipe.dst.ours + 1) % pipe.dst.entries;
    ++posted;
  }
  if (posted) {
    chipWrite(ce, io, pipe.dst.r2, pointerOf(pipe.dst, pipe.dst.ours));
    ce.posted += posted;
  }
  return posted;
}

// A free outbound buffer to build a message in; -1 when all of them are in flight.
inline int ceClaim(Ce &ce)
{
  for (unsigned i = 0; i < kCeSendBuffers; ++i)
    if (!ce.tx[i].busy && ce.tx[i].va) {
      ce.tx[i].busy = true;
      ce.tx[i].length = 0;
      return int(i);
    }
  ++ce.refused;
  return -1;
}

inline void ceRelease(Ce &ce, unsigned buffer)
{
  if (buffer < kCeSendBuffers) ce.tx[buffer].busy = false;
}

// The claimed buffer, `length` bytes of it, on a pipe's source ring; one pointer write. `meta` comes back in the status entry of
// the firmware's answer on this chip family, so the owner may use it to tell its own messages apart. False when the ring is full
// (the claim is then given back) or the pipe has no source ring.
inline bool ceSend(Ce &ce, const ChipIo &io, unsigned index, unsigned buffer, uint32_t length, uint32_t meta)
{
  using namespace cedetail;
  if (index >= kCeHostPipeCount || buffer >= kCeSendBuffers) return false;
  CePipe &pipe = ce.pipes[index];
  CeBuffer &out = ce.tx[buffer];
  if (!pipe.hasSrc || !out.busy || !out.va || !length || length > out.bytes || length > kCeDescLenMask) return false;
  if (!freeEntries(pipe.src)) {
    ceRelease(ce, buffer);
    return false;
  }
  uint8_t *desc = pipe.src.va + pipe.src.ours * pipe.src.words * 4;
  put32(desc, uint32_t(out.bus & kRingAddrLowMask));
  put32(desc + 4, uint32_t((out.bus >> kRingAddrHiShift) & kCeDescAddrHiMask) | (length & kCeDescLenMask) << kCeDescLenShift);
  put32(desc + 8, meta & kCeDescMetaMask);
  put32(desc + 12, (pipe.src.ringId & 0xffu) << kCeDescRingIdShift);
  pipe.txSlot[pipe.src.ours] = buffer;
  out.length = length;
  pipe.src.ours = (pipe.src.ours + 1) % pipe.src.entries;
  chipWrite(ce, io, pipe.src.r2, pointerOf(pipe.src, pipe.src.ours));
  ++ce.sent;
  ce.bytesOut += length;
  return true;
}

// One turn: every pipe's completions and every filled buffer, handed to `deliver(kind, pipe, va, length, meta)`. A received
// buffer stays the owner's until it calls cePostRx again, so nothing can overwrite a message being read. Returns how many events
// were seen.
template <class Deliver>
inline unsigned cePoll(Ce &ce, const ChipIo &io, Deliver deliver)
{
  using namespace cedetail;
  unsigned seen = 0;
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    CePipe &pipe = ce.pipes[i];
    // The messages the chip has sent for us: the source ring's entries up to its own pointer are free again — but never more
    // of them than the host actually wrote, so that a pointer the chip has not moved (or has moved too far) cannot free a
    // buffer that is still being filled.
    if (pipe.hasSrc) {
      const uint32_t theirs = slotOf(pipe.src, load(pipe.src.theirs));
      uint32_t inFlight = (pipe.src.ours + pipe.src.entries - pipe.src.taken) % pipe.src.entries;
      while (pipe.src.taken != theirs && inFlight--) {
        const uint32_t buffer = pipe.txSlot[pipe.src.taken];
        pipe.src.taken = (pipe.src.taken + 1) % pipe.src.entries;
        if (buffer < kCeSendBuffers && ce.tx[buffer].busy) {
          ce.tx[buffer].busy = false;
          ++ce.completions;
          deliver(kCeSent, pipe.pipe, ce.tx[buffer].va, ce.tx[buffer].length, buffer);
        } else {
          ++ce.dropped;
        }
        ++seen;
      }
    }
    if (!pipe.hasDst) continue;
    // the buffers the chip has filled: one status descriptor each, in the order the buffers were posted
    const uint32_t theirs = slotOf(pipe.status, load(pipe.status.theirs));
    bool moved = false;
    while (pipe.status.ours != theirs) {
      const uint8_t *desc = pipe.status.va + pipe.status.ours * pipe.status.words * 4;
      const uint32_t flags = get32(desc), meta = get32(desc + 12);
      const uint32_t length = (flags >> kCeStatusLenShift) & kCeStatusLenMask;
      pipe.status.ours = (pipe.status.ours + 1) % pipe.status.entries;
      moved = true;
      ++seen;
      const uint32_t slot = pipe.dst.taken;
      pipe.dst.taken = (pipe.dst.taken + 1) % pipe.dst.entries;
      const uint32_t buffer = pipe.slot[slot];
      // A length of zero, or one larger than the buffer, is the chip or the status entry disagreeing with the host: the
      // buffer is given back and nothing of it is delivered.
      if (buffer >= pipe.rxCount || !pipe.rx[buffer].busy || !length || length > pipe.rx[buffer].bytes) {
        ++ce.dropped;
        if (buffer < pipe.rxCount) pipe.rx[buffer].busy = false;
        continue;
      }
      pipe.rx[buffer].busy = false;
      pipe.rx[buffer].length = length;
      ++ce.received;
      ce.bytesIn += length;
      deliver(kCeReceived, pipe.pipe, pipe.rx[buffer].va, length, meta & kCeDescMetaMask);
    }
    if (moved) chipWrite(ce, io, pipe.status.r2 + 4, pointerOf(pipe.status, pipe.status.ours));
  }
  return seen;
}

// The teardown: every ring disabled, so the chip walks none of them any more. The window itself is never freed (wifi.md section
// 10.10), and the buffers stay where they are: only a reset guarantees the chip has stopped.
inline void ceStop(Ce &ce, const ChipIo &io)
{
  using namespace cedetail;
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    CePipe &pipe = ce.pipes[i];
    if (pipe.hasSrc) chipWrite(ce, io, pipe.src.r0 + kRingMisc, 0);
    if (!pipe.hasDst) continue;
    chipWrite(ce, io, pipe.dst.r0 + kRingMisc, 0);
    chipWrite(ce, io, pipe.status.r0 + kRingMisc, 0);
  }
}

// True when nothing of ours is in the chip's hands any more: every outbound buffer has had its completion. The teardown waits
// for it before any ring is disabled.
inline bool ceIdle(const Ce &ce)
{
  for (const CeBuffer &b : ce.tx)
    if (b.busy) return false;
  return true;
}

// Which of our pipes carries a given pipe number (the service tables of level 5 name pipe numbers, not indexes).
inline int ceIndexOf(uint32_t pipe)
{
  for (unsigned i = 0; i < kCeHostPipeCount; ++i)
    if (kCeHostPipes[i].pipe == pipe) return int(i);
  return -1;
}

}  // namespace pianowifi
