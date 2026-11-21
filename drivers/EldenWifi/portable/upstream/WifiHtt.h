// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi, the firmware's data interface (HTT) as far as the receive buffers need it (P23, docs/drivers/wifi.md §10.28): the
// version exchange, the receive rings in host memory with their buffers, the ring set-up messages that announce them, and the
// turn that keeps the rings the hardware consumes from running dry. All as portable pieces the owner steps (host tests:
// tests/wmi_host.cpp, against a firmware model that reads the rings back). New code for this repository; the message types,
// the field layouts, the ring identifiers and kinds and the entry formats are wire facts of WifiHw.h, read from the Ubuntu
// kernel of §3 for those facts only — no code, comment or table of it is here.
//
// Why the rings exist before anything is received: on this chip family the receive DMA takes its buffers from rings the host
// fills — a host-to-firmware ring of empty buffers, from which the firmware fills one buffer ring per radio — so a radio
// with no host buffers hears every beacon of a scan and keeps none of them (the 2026-11-13 02:05 boot: a full scan, every
// channel visited, no management frame at all).
//
// The rings (all in the 32-bit window; every pointer in host memory, because they belong to the radio's own units):
//   refill        host -> firmware, 512 buffers of 2 KiB: the host writes the head, the firmware the tail
//   radio 0, 1    firmware -> receive DMA, 512 entries each, empty: the firmware fills them from the refill ring
//   errors        receive DMA -> host, 128 entries: the host moves its tail up to the hardware's head every turn (nothing of
//                 it is read at this level)
//   status 0, 1   host -> receive DMA, 63 buffers each: the hardware writes its per-PPDU status into them; every buffer it
//                 has taken is given back on the next turn (nothing of it is read at this level either)
// Nothing here allocates, maps or sleeps.
#pragma once
#include <stdint.h>
#include "WifiHw.h"
#include "WifiMhi.h"

namespace pianowifi {

struct HttRing {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t entries = 0, entryWords = 0;
  uint32_t htt = 0, kind = 0, radio = 0;      // what the set-up message says: its identifier, kind and radio field
  volatile uint32_t *head = nullptr, *tail = nullptr;
  uint64_t headBus = 0, tailBus = 0;
  uint32_t ours = 0;                          // the slot this host writes next (a ring it produces into) or reads next
  bool planned = false, announced = false;
};

constexpr unsigned kHttRings = 6;             // refill, two radio buffer rings, errors, two status rings
enum HttRingIndex : unsigned { kHttRefill = 0, kHttMacBuf0 = 1, kHttMacBuf1 = 2, kHttErrDst = 3, kHttStatus0 = 4, kHttStatus1 = 5 };

// A peer the firmware's data interface named (level 7 waits for its own): the device, the peer identifier the data path
// carries, the hardware peer, and the address — kept for the join's own comparison, never logged.
// The second and third forms also carry the address search entry the transmit descriptor names (its index, the hardware
// peer, and its hash); the first carries none (hasSearch false: the transmit side then names index 0, as this chip's host does).
struct HttPeerMap {
  uint32_t type = 0, vdevId = 0, peerId = 0, hwPeerId = 0, astHash = 0;
  uint8_t mac[6] = {};
  bool unmapped = false, hasSearch = false;
};
constexpr unsigned kHttPeerMapsKept = 4;

struct HttRx {
  HttRing ring[kHttRings];
  HttPeerMap peer[kHttPeerMapsKept];   // the last four peer maps and unmaps, the newest at (peerEvents - 1) % 4
  uint32_t peerEvents = 0, peerUnmaps = 0;
  // the buffers: the refill ring's, then each status ring's
  uint64_t refillBus[kRxRefillEntries] = {};
  uint8_t *refillVa[kRxRefillEntries] = {};   // level 8 reads the received frames out of them
  uint64_t statusBus[kRxRadios][kRxMonStatusEntries] = {};
  uint32_t statusSlotBuffer[kRxRadios][kRxMonStatusEntries] = {};   // status ring slot -> which of its buffers sits there
  uint32_t rbm = kRxBufRbmFw;
  // what the firmware said, and the counters for the log
  bool versionSeen = false;
  uint32_t versionMajor = 0, versionMinor = 0;
  uint32_t t2hMessages = 0, t2hTypes[8] = {}, t2hTypeCount = 0, peerMaps = 0;
  uint32_t refillPosted = 0, refillTaken = 0, statusRecycled = 0, errorsSeen = 0, macBufFilled[kRxRadios] = {};
  uint32_t announced = 0;
};

namespace httdetail {

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
inline uint32_t load(volatile uint32_t *p) { return p ? *p : 0; }
inline void store(volatile uint32_t *p, uint32_t v)
{
  if (p) *p = v;
}

// A buffer's entry: its address and the manager it returns to, and a cookie that names it.
inline void putBuffer(uint8_t *entry, uint64_t bus, uint32_t rbm, uint32_t cookie)
{
  put32(entry, uint32_t(bus & 0xffffffffu));
  put32(entry + 4, uint32_t((bus >> 32) & kRxBufAddrHiMask) | (rbm & 0xfu) << kRxBufRbmShift |
                       (cookie & kRxBufCookieMask) << kRxBufCookieShift);
}

inline bool planRing(HttRing &r, Arena &arena, uint32_t entries, uint32_t entryWords, uint32_t htt, uint32_t kind,
                     uint32_t radio, uint8_t *pointers, uint64_t pointersBus, uint32_t &pointerIndex)
{
  uint64_t bus = 0;
  uint8_t *va = arenaAlloc(arena, entries * entryWords * 4, &bus);
  if (!va) return false;
  r.va = va;
  r.bus = bus;
  r.entries = entries;
  r.entryWords = entryWords;
  r.htt = htt;
  r.kind = kind;
  r.radio = radio;
  r.head = reinterpret_cast<volatile uint32_t *>(pointers + 4 * pointerIndex);
  r.headBus = pointersBus + 4 * pointerIndex;
  ++pointerIndex;
  r.tail = reinterpret_cast<volatile uint32_t *>(pointers + 4 * pointerIndex);
  r.tailBus = pointersBus + 4 * pointerIndex;
  ++pointerIndex;
  store(r.head, 0);
  store(r.tail, 0);
  r.ours = 0;
  r.planned = true;
  return true;
}

inline uint32_t slotOf(const HttRing &r, uint32_t words) { return r.entryWords ? (words / r.entryWords) % r.entries : 0; }

}  // namespace httdetail

// The rings and their buffers out of the window. False when it has no room (nothing the chip knows of has been changed then).
inline bool httPlan(HttRx &rx, Arena &arena, bool rbmSw1)
{
  using namespace httdetail;
  renew(rx);
  rx.rbm = rbmSw1 ? kRxBufRbmSw1 : kRxBufRbmFw;
  uint64_t pointersBus = 0;
  uint8_t *pointers = arenaAlloc(arena, 4 * 2 * kHttRings, &pointersBus);
  if (!pointers) return false;
  uint32_t index = 0;
  // The refill ring belongs to radio 0 with no offset (a host-to-firmware ring); the receive DMA's rings carry the radio's
  // number plus one, as the chip's own host writes them.
  if (!planRing(rx.ring[kHttRefill], arena, kRxRefillEntries, kRxBufEntryWords, kHttRingHost1ToFwRxbuf, kHttSwToSw, 0, pointers,
                pointersBus, index))
    return false;
  for (uint32_t radio = 0; radio < kRxRadios; ++radio)
    if (!planRing(rx.ring[kHttMacBuf0 + radio], arena, kRxMacBufEntries, kRxBufEntryWords, kHttRingRxdmaHostBuf, kHttSwToHw,
                  radio + 1, pointers, pointersBus, index))
      return false;
  if (!planRing(rx.ring[kHttErrDst], arena, kRxErrDstEntries, kRxDmaDstEntryWords, kHttRingRxdmaNonMonitorDest, kHttHwToSw, 1,
                pointers, pointersBus, index))
    return false;
  for (uint32_t radio = 0; radio < kRxRadios; ++radio)
    if (!planRing(rx.ring[kHttStatus0 + radio], arena, kRxMonStatusEntries, kRxBufEntryWords, kHttRingRxdmaMonitorStatus,
                  kHttSwToHw, radio + 1, pointers, pointersBus, index))
      return false;
  // The buffers: 2 KiB each, from the window (at least 128-byte aligned: the arena aligns them to their own size).
  for (uint32_t i = 0; i + 1 < kRxRefillEntries; ++i)
    if (!(rx.refillVa[i] = arenaAlloc(arena, kRxBufferBytes, &rx.refillBus[i]))) return false;
  for (uint32_t radio = 0; radio < kRxRadios; ++radio)
    for (uint32_t i = 0; i + 1 < kRxMonStatusEntries; ++i)
      if (!arenaAlloc(arena, kRxBufferBytes, &rx.statusBus[radio][i])) return false;
  return true;
}

// Every buffer into its ring and the head pointers written — before the rings are announced, as the chip's own host has them
// full when the firmware first looks. A ring always keeps one entry free (the two pointers alone tell full from empty).
inline void httFill(HttRx &rx)
{
  using namespace httdetail;
  HttRing &refill = rx.ring[kHttRefill];
  for (uint32_t i = 0; i + 1 < refill.entries; ++i) {
    putBuffer(refill.va + i * refill.entryWords * 4, rx.refillBus[i], rx.rbm, i);
    ++rx.refillPosted;
  }
  refill.ours = refill.entries - 1;
  store(refill.head, refill.ours * refill.entryWords);
  for (uint32_t radio = 0; radio < kRxRadios; ++radio) {
    HttRing &status = rx.ring[kHttStatus0 + radio];
    for (uint32_t i = 0; i + 1 < status.entries; ++i) {
      // the cookie names the radio and the buffer: nothing reads it back at this level, but a dump would
      putBuffer(status.va + i * status.entryWords * 4, rx.statusBus[radio][i], rx.rbm, 0x80000u | radio << 12 | i);
      rx.statusSlotBuffer[radio][i] = i;
    }
    status.ours = status.entries - 1;
    store(status.head, status.ours * status.entryWords);
  }
}

// One ring's set-up message (13 words), as the data interface's payload. Returns its length, 0 when it does not fit.
inline uint32_t httBuildSrngSetup(uint8_t *at, uint32_t capacity, const HttRing &r)
{
  using namespace httdetail;
  const uint32_t bytes = kHttSrngSetupWords * 4;
  if (!at || capacity < bytes || !r.planned) return 0;
  for (uint32_t i = 0; i < bytes; ++i) at[i] = 0;
  put32(at + 0, kHttMsgSrngSetup | (r.radio & 0xffu) << 8 | (r.htt & 0xffu) << 16 | (r.kind & 0xffu) << 24);
  put32(at + 4, uint32_t(r.bus & 0xffffffffu));
  put32(at + 8, uint32_t(r.bus >> 32));
  put32(at + 12, ((r.entries * r.entryWords) & 0xffffu) | (r.entryWords & 0xffu) << 16 |
                     (r.kind == kHttSwToHw ? kHttSrngLoopCountDisable : 0u));
  put32(at + 16, uint32_t(r.headBus & 0xffffffffu));
  put32(at + 20, uint32_t(r.headBus >> 32));
  put32(at + 24, uint32_t(r.tailBus & 0xffffffffu));
  put32(at + 28, uint32_t(r.tailBus >> 32));
  // MSI address and data, interrupt batching and the low threshold: none (this host polls)
  return bytes;
}

// The version request: the message type and the one option the chip's own host sends.
inline uint32_t httBuildVersionReq(uint8_t *at, uint32_t capacity)
{
  using namespace httdetail;
  if (!at || capacity < 8) return 0;
  put32(at, kHttMsgVersionReq);
  put32(at + 4, kHttOptionTclMetadataVersion | kHttOptionTclMetadataLength << 8 | kHttTclMetadataV2 << 16);
  return 8;
}

// A message from the data interface: the version's answer is read, every other type is counted (a peer map among them, which
// is level 7's), nothing is acted on.
inline void httReceive(HttRx &rx, const uint8_t *payload, uint32_t length)
{
  using namespace httdetail;
  if (!payload || length < 4) return;
  ++rx.t2hMessages;
  const uint32_t word0 = get32(payload);
  const uint32_t type = word0 & 0xffu;
  bool known = false;
  for (uint32_t i = 0; i < rx.t2hTypeCount; ++i) known = known || rx.t2hTypes[i] == type;
  if (!known && rx.t2hTypeCount < sizeof rx.t2hTypes / sizeof rx.t2hTypes[0]) rx.t2hTypes[rx.t2hTypeCount++] = type;
  if (type == kHttT2hVersionConf) {
    rx.versionSeen = true;
    rx.versionMinor = (word0 >> 8) & 0xffu;
    rx.versionMajor = (word0 >> 16) & 0xffu;
  } else if (type == kHttT2hPeerMap || type == kHttT2hPeerMap2 || type == kHttT2hPeerMap3 || type == kHttT2hPeerUnmap ||
             type == kHttT2hPeerUnmap2) {
    if (length < 12) return;
    const bool unmap = type == kHttT2hPeerUnmap || type == kHttT2hPeerUnmap2;
    HttPeerMap &p = rx.peer[rx.peerEvents % kHttPeerMapsKept];
    renew(p);
    p.type = type;
    p.unmapped = unmap;
    p.vdevId = (word0 >> 8) & 0xffu;
    p.peerId = (word0 >> 16) & 0xffffu;
    const uint32_t lo = get32(payload + 4), word2 = get32(payload + 8);
    for (unsigned i = 0; i < 4; ++i) p.mac[i] = uint8_t(lo >> (8 * i));
    p.mac[4] = uint8_t(word2 & 0xffu);
    p.mac[5] = uint8_t((word2 >> 8) & 0xffu);
    if (!unmap) {
      const uint32_t word3 = length >= 16 ? get32(payload + 12) : 0;
      if (type == kHttT2hPeerMap3) {
        p.hwPeerId = word3 & 0xffffu;
        p.astHash = word3 >> 16;
      } else {
        p.hwPeerId = (word2 >> 16) & 0xffffu;
        p.astHash = type == kHttT2hPeerMap2 ? (word3 & 0xffffu) : 0;
      }
      p.hasSearch = type != kHttT2hPeerMap && length >= 16;
      ++rx.peerMaps;
    } else {
      ++rx.peerUnmaps;
    }
    ++rx.peerEvents;
  }
}

// Level 8: the refill ring kept full. A buffer that came back to the host (out of the reorder unit's ring or a release ring,
// WifiDp.h) goes into the refill ring again; the firmware hands it on to a radio's buffer ring. One entry always stays free
// (the two pointers alone tell full from empty).
inline uint32_t httRefillFree(const HttRx &rx)
{
  using namespace httdetail;
  const HttRing &r = rx.ring[kHttRefill];
  if (!r.planned || !r.entries) return 0;
  const uint32_t tail = r.announced ? slotOf(r, load(r.tail)) : 0;
  const uint32_t used = (r.ours + r.entries - tail) % r.entries;
  return r.entries - 1 - used;
}

// Buffer `buffer` (its cookie) into the refill ring again; false when it is not one of the refill ring's or there is no room.
inline bool httRefillPost(HttRx &rx, uint32_t buffer)
{
  using namespace httdetail;
  HttRing &r = rx.ring[kHttRefill];
  if (buffer + 1 >= kRxRefillEntries || !r.planned) return false;
  if (!httRefillFree(rx)) return false;
  putBuffer(r.va + r.ours * r.entryWords * 4, rx.refillBus[buffer], rx.rbm, buffer);
  r.ours = (r.ours + 1) % r.entries;
  store(r.head, r.ours * r.entryWords);
  ++rx.refillPosted;
  return true;
}

// The newest peer map for an address and a device, or null.
inline const HttPeerMap *httPeerMapOf(const HttRx &rx, uint32_t vdevId, const uint8_t *mac)
{
  const uint32_t kept = rx.peerEvents < kHttPeerMapsKept ? rx.peerEvents : kHttPeerMapsKept;
  for (uint32_t i = 0; i < kept; ++i) {
    const HttPeerMap &p = rx.peer[(rx.peerEvents - 1 - i) % kHttPeerMapsKept];
    bool same = p.vdevId == vdevId || p.unmapped;   // an unmap names no device
    for (unsigned k = 0; k < 6 && same; ++k) same = p.mac[k] == mac[k];
    if (same) return p.unmapped ? nullptr : &p;
  }
  return nullptr;
}

// One turn: the refill ring's tail read (what the firmware has taken so far), each status ring's buffers the hardware took
// given back, the error ring's tail moved up to the hardware's head, and each radio's buffer ring's fill noted. Nothing of
// what the hardware wrote is read: at this level the rings exist so that the radio can receive at all.
inline void httTurn(HttRx &rx)
{
  using namespace httdetail;
  HttRing &refill = rx.ring[kHttRefill];
  if (refill.announced) {
    const uint32_t tail = slotOf(refill, load(refill.tail));
    rx.refillTaken = tail;   // how far the firmware has read (it wraps only after the whole ring)
  }
  for (uint32_t radio = 0; radio < kRxRadios; ++radio) {
    HttRing &status = rx.ring[kHttStatus0 + radio];
    if (!status.announced) continue;
    const uint32_t tail = slotOf(status, load(status.tail));
    // The free slots run from our head up to one before the hardware's tail; every buffer the hardware took between its old
    // and its new tail goes back in, in the order it was taken.
    uint32_t moved = 0;
    while ((status.ours + 1) % status.entries != tail) {
      // the oldest slot the hardware has taken is the one right after our head
      const uint32_t takenSlot = (status.ours + 1) % status.entries;
      const uint32_t buffer = rx.statusSlotBuffer[radio][takenSlot];
      putBuffer(status.va + status.ours * status.entryWords * 4, rx.statusBus[radio][buffer % (kRxMonStatusEntries - 1)],
                rx.rbm, 0x80000u | radio << 12 | buffer);
      rx.statusSlotBuffer[radio][status.ours] = buffer;
      status.ours = (status.ours + 1) % status.entries;
      ++moved;
      if (moved == status.entries) break;
    }
    if (moved) {
      store(status.head, status.ours * status.entryWords);
      rx.statusRecycled += moved;
    }
  }
  HttRing &errors = rx.ring[kHttErrDst];
  if (errors.announced) {
    const uint32_t head = slotOf(errors, load(errors.head));
    if (head != errors.ours) {
      rx.errorsSeen += (head + errors.entries - errors.ours) % errors.entries;
      errors.ours = head;
      store(errors.tail, errors.ours * errors.entryWords);
    }
  }
  for (uint32_t radio = 0; radio < kRxRadios; ++radio) {
    const HttRing &mac = rx.ring[kHttMacBuf0 + radio];
    if (mac.announced) rx.macBufFilled[radio] = slotOf(mac, load(mac.head));
  }
}

}  // namespace pianowifi
