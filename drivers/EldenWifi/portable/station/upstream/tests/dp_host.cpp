// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test of PianoWifi level 8, the data path (WifiDp.h, the level 8 parts of WifiHtt.h): the rings' registers as the chip
// reads them, the idle link list, the reorder unit's set-up, the receive ring selection message, a received MSDU read out of
// its buffer (an EAPOL frame and an Ethernet one, each delivered and its buffer posted again), the frames that must not be
// delivered (not done, errors, null data, a bad cookie, a link descriptor), the release rings' buffers given back, a frame
// sent (every field of its descriptor) and its completion, and the transmit side's limits.
//   c++ -std=c++20 -Wall -Wextra -Werror -I.. dp_host.cpp -o /tmp/dp_host && /tmp/dp_host
#include "WifiDp.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>

using namespace pianowifi;
static int failures;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

static void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}
static uint32_t get32(const uint8_t *at)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[i]) << (8 * i);
  return v;
}

// The chip's registers: every write kept, a read gives the last value written (or what the test put there).
struct Chip {
  std::map<uint32_t, uint32_t> regs;
  std::vector<std::pair<uint32_t, uint32_t>> writes;
};
static uint32_t chipRead(void *ctx, uint32_t address)
{
  auto &c = *static_cast<Chip *>(ctx);
  auto it = c.regs.find(address);
  return it == c.regs.end() ? 0 : it->second;
}
static void chipWrite(void *ctx, uint32_t address, uint32_t value)
{
  auto &c = *static_cast<Chip *>(ctx);
  c.regs[address] = value;
  c.writes.push_back({address, value});
}
static bool written(const Chip &c, uint32_t address) { return c.regs.count(address) != 0; }

static const uint8_t kOwn[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x04};
static const uint8_t kAp[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x30};

// A received MSDU as the hardware leaves it: the descriptor's fields in the buffer, the frame after it and its padding.
static void fillRx(HttRx &rx, uint32_t cookie, const std::vector<uint8_t> &frame, uint32_t pad, uint32_t info13 = 0,
                   bool done = true, uint32_t decap = kRxDecapEthernet)
{
  uint8_t *va = rx.refillVa[cookie];
  std::memset(va, 0, kRxBufferBytes);
  put32(va + kRxDescInfo14, done ? kRxDescMsduDone : 0);
  put32(va + kRxDescInfo13, info13);
  const uint32_t info5 = (pad & kRxDescL3PadMask) << kRxDescL3PadShift | kRxDescFirstMsdu | kRxDescLastMsdu;
  va[kRxDescInfo5] = uint8_t(info5);
  va[kRxDescInfo5 + 1] = uint8_t(info5 >> 8);
  put32(va + kRxDescInfo10, uint32_t(frame.size()) & kRxDescMsduLenMask);
  put32(va + kRxDescInfo11, decap << kRxDescDecapShift);
  std::memcpy(va + kRxDescBytes + pad, frame.data(), frame.size());
}

// One REO destination entry naming refill buffer `cookie` (its address as the refill ring gave it, or a wrong one).
static void reoEntry(Dp &dp, uint32_t slot, uint64_t bus, uint32_t cookie, uint32_t length, uint32_t msdu = kDpMsduFirst | kDpMsduLast,
                     uint32_t info0 = 0)
{
  uint8_t *e = dp.reo.va + slot * dp.reo.words * 4;
  std::memset(e, 0, dp.reo.words * 4);
  put32(e, uint32_t(bus));
  put32(e + 4, (uint32_t(bus >> 32) & 0xffu) | kDpRbmSw1 << 8 | cookie << 12);
  put32(e + 16, msdu | (length & kDpMsduLenMask) << kDpMsduLenShift);
  put32(e + 28, info0);
}

static std::vector<uint8_t> ethFrame(uint16_t type, uint32_t payload, uint8_t fill)
{
  std::vector<uint8_t> f(14 + payload, fill);
  std::memcpy(f.data(), kOwn, 6);
  std::memcpy(f.data() + 6, kAp, 6);
  f[12] = uint8_t(type >> 8);
  f[13] = uint8_t(type);
  return f;
}

int main()
{
  // ---- the window: one arena, as the kext's (bus addresses above 4 GiB, to see the high bits carried)
  const uint32_t bytes = 8u << 20;
  uint8_t *window = static_cast<uint8_t *>(std::aligned_alloc(1u << 20, bytes));
  Arena arena;
  arenaInit(arena, window, 0x1'2340'0000ull, bytes);
  HttRx rx;
  CHECK(httPlan(rx, arena, true));
  httFill(rx);
  CHECK(rx.rbm == kRxBufRbmSw1);
  for (uint32_t i = 0; i + 1 < kRxRefillEntries; ++i) CHECK(rx.refillVa[i] && rx.refillVa[i] == window + (rx.refillBus[i] - arena.bus));
  Dp dp;
  CHECK(dpPlan(dp, arena, &rx));
  CHECK(dp.planned && dp.linkDescs == kDpIdleEntries - 1);
  CHECK((dp.linkBus & 127) == 0);
  Chip chip;
  ChipIo io{&chip, chipRead, chipWrite};
  chip.regs[kDpReoMiscCtrl] = 0xffffffffu;   // what is there already: only the fragment and BAR fields change
  chip.regs[kDpReoGenEnable] = 0x1;
  dpProgram(dp, io);
  CHECK(dp.programmed);

  // ---- the rings' registers
  // the transmit ring (host -> TCL): base, size in words, entry size, no ring identifier, the tail pointer's address
  CHECK(chip.regs[kDpTcl1R0] == uint32_t(dp.tcl.bus));
  CHECK(chip.regs[kDpTcl1R0 + kRingBaseMsb] == (uint32_t(dp.tcl.bus >> 32) | (kDpTclEntries * 8) << kRingBaseMsbSizeShift));
  CHECK(chip.regs[kDpTcl1R0 + kRingId] == 8);
  CHECK(chip.regs[kDpTcl1R0 + kSrcRingTpAddrLo] == uint32_t(dp.tcl.theirsBus));
  CHECK(chip.regs[kDpTcl1R0 + kSrcRingTpAddrHi] == uint32_t(dp.tcl.theirsBus >> 32));
  CHECK(chip.regs[kDpTcl1R0 + kRingMisc] == (kRingMiscEnable | kRingMiscLoopCountDisable));
  // its completions (WBM2SW0, ring 128), the received MSDUs (REO2SW1, ring 1), the exceptions (REO2SW0, ring 0)
  CHECK(chip.regs[kDpWbm2Sw0R0 + kRingId] == (8u | 128u << kRingIdRingIdShift));
  CHECK(chip.regs[kDpWbm2Sw0R0 + kDstRingHpAddrLo] == uint32_t(dp.txComp.theirsBus));
  CHECK(chip.regs[kDpWbm2Sw0R0 + kRingMisc] == kRingMiscEnable);
  CHECK(chip.regs[kDpReo2Sw1R0] == uint32_t(dp.reo.bus));
  CHECK(chip.regs[kDpReo2Sw1R0 + kRingId] == (8u | 1u << kRingIdRingIdShift));
  CHECK(chip.regs[kDpReo2Sw1R0 + kRingBaseMsb] == (uint32_t(dp.reo.bus >> 32) | (kDpReoEntries * 8) << kRingBaseMsbSizeShift));
  CHECK(chip.regs[kDpReo2Sw0R0 + kRingId] == 8u);
  CHECK(chip.regs[kDpReo2Sw0R0 + kDstRingHpAddrLo] == uint32_t(dp.reoExc.theirsBus));
  // the receive error release ring at its stride (WBM2SW3 at +3 * 0x78, ring 131); WBM2SW1 is never touched
  CHECK(chip.regs[kDpWbm2Sw0R0 + 3 * 0x78 + kRingId] == (8u | 131u << kRingIdRingIdShift));
  for (uint32_t off = 0; off < 0x78; off += 4) CHECK(!written(chip, kDpWbm2Sw0R0 + 0x78 + off));
  CHECK(!written(chip, kDpWbm2Sw0R2 + 8) && !written(chip, kDpWbm2Sw0R2 + 12));
  CHECK(written(chip, kDpWbm2Sw0R2 + 3 * 8) && written(chip, kDpWbm2Sw0R2 + 3 * 8 + 4));
  // every ring's pointers in host memory are distinct
  const volatile uint32_t *ptrs[] = {dp.tcl.theirs, dp.txComp.theirs, dp.reo.theirs, dp.reoExc.theirs, dp.rel3.theirs,
                                     dp.idle.theirs};
  for (unsigned i = 0; i < 6; ++i)
    for (unsigned k = i + 1; k < 6; ++k) CHECK(ptrs[i] != ptrs[k]);
  // the idle link ring: no ring identifier check, no tail address, every link descriptor in it, its head after the last one
  CHECK(chip.regs[kDpIdleLinkR0 + kRingMisc] == (kRingMiscEnable | kRingMiscLoopCountDisable | kRingMiscNoRingId));
  CHECK(!written(chip, kDpIdleLinkR0 + kSrcRingTpAddrLo) && !written(chip, kDpIdleLinkR0 + kSrcRingTpAddrHi));
  CHECK(chip.regs[kDpIdleLinkR0 + kRingId] == 2);
  CHECK(chip.regs[kDpIdleLinkR2] == dp.linkDescs * 2);
  for (uint32_t i : {0u, 1u, 500u, dp.linkDescs - 1}) {
    const uint8_t *e = dp.idle.va + i * 8;
    const uint64_t bus = dp.linkBus + uint64_t(i) * kDpLinkDescBytes;
    CHECK(get32(e) == uint32_t(bus));
    CHECK(get32(e + 4) == ((uint32_t(bus >> 32) & 0xffu) | 1u << 8 | i << 12));
  }
  // the reorder unit: aging on (and what was set kept), fragments and BARs to REO2SW0, the thresholds, the hash all to SW1
  CHECK(chip.regs[kDpReoGenEnable] == (0x1u | kDpReoGenAgingList | kDpReoGenAgingFlush));
  CHECK(chip.regs[kDpReoMiscCtrl] == (0xffffffffu & ~(kDpReoMiscFragMask | kDpReoMiscBarMask)));
  CHECK(chip.regs[kDpReoAgingIx0] == 100000 && chip.regs[kDpReoAgingIx0 + 12] == 40000);
  CHECK(chip.regs[kDpReoDestIx2] == 0x11111111u && chip.regs[kDpReoDestIx3] == 0x11111111u);
  CHECK(!dpCookieConversionOn(dp));
  // the idle ring's head is written after its entries: the last write to it
  {
    size_t lastEntryWrite = 0, headWrite = 0;
    for (size_t i = 0; i < chip.writes.size(); ++i) {
      if (chip.writes[i].first == kDpIdleLinkR0 + kRingMisc) lastEntryWrite = i;
      if (chip.writes[i].first == kDpIdleLinkR2 && chip.writes[i].second) headWrite = i;
    }
    CHECK(headWrite > lastEntryWrite);
  }

  // ---- the receive ring selection for radio buffer ring 1 (the radio field 2)
  {
    uint8_t m[128] = {};
    CHECK(httBuildRxSelection(m, 8, 0) == 0);
    CHECK(httBuildRxSelection(m, sizeof m, 1) == 72);
    CHECK(get32(m) == (0x0cu | 2u << 8 | 0u << 16 | 1u << 26 | 1u << 28));
    CHECK(get32(m + 4) == 2048);
    CHECK(get32(m + 8) == 0 && get32(m + 12) == 0);
    CHECK(get32(m + 16) == 1u << 24);
    CHECK(get32(m + 20) == (1u << 18 | 1u << 21 | 1u << 24));
    CHECK(get32(m + 24) == 0xdu);
    CHECK(get32(m + 28) == (392u | 264u << 16));
    CHECK(get32(m + 32) == 140u << 16);
    CHECK(get32(m + 36) == 0);
    for (unsigned i = 10; i < 18; ++i) CHECK(get32(m + 4 * i) == 0);
  }

  // ---- the receive side: the firmware has taken 20 buffers out of the refill ring (its tail), so 20 slots are free again
  HttRing &refill = rx.ring[kHttRefill];
  refill.announced = true;
  *refill.tail = 20 * refill.entryWords;
  CHECK(httRefillFree(rx) == 20);
  const uint32_t refillBefore = refill.ours;
  std::vector<uint8_t> eapol = ethFrame(kEtherTypeEapol, 99 - 14, 0x5a);
  eapol[14] = 2;   // EAPOL version 2, type 3 (Key)
  eapol[15] = 3;
  std::vector<uint8_t> ip = ethFrame(0x0800, 300, 0x11);
  fillRx(rx, 5, eapol, 2);
  fillRx(rx, 6, ip, 0);
  reoEntry(dp, 0, rx.refillBus[5], 5, uint32_t(eapol.size()));
  reoEntry(dp, 1, rx.refillBus[6], 6, uint32_t(ip.size()));
  *dp.reo.theirs = 2 * dp.reo.words;
  struct Got {
    uint32_t kind, length;
    std::vector<uint8_t> bytes;
  };
  std::vector<Got> got;
  auto deliver = [&](uint32_t kind, const uint8_t *frame, uint32_t length) {
    got.push_back({kind, length, std::vector<uint8_t>(frame, frame + length)});
  };
  CHECK(dpPoll(dp, io, deliver) == 2);
  CHECK(got.size() == 2);
  CHECK(got[0].kind == kDpRxEapol && got[0].length == 99 && got[0].bytes == eapol);
  CHECK(got[1].kind == kDpRxEthernet && got[1].length == ip.size() && got[1].bytes == ip);
  CHECK(dp.st.rxEapol == 1 && dp.st.rxFrames == 2 && dp.st.lastEapolLength == 99 && dp.st.rxRecycled == 2);
  CHECK(chip.regs[kDpReo2Sw1R2 + 4] == 2 * 8);          // our tail, in words
  CHECK(refill.ours == (refillBefore + 2) % refill.entries);
  CHECK(*refill.head == refill.ours * refill.entryWords);
  // the posted entries name the same buffers with the same cookies and software ring 1
  {
    const uint8_t *e = refill.va + refillBefore * refill.entryWords * 4;
    CHECK(get32(e) == uint32_t(rx.refillBus[5]));
    CHECK(((get32(e + 4) >> kRxBufRbmShift) & 0xf) == kDpRbmSw1);
    CHECK(((get32(e + 4) >> kRxBufCookieShift) & kRxBufCookieMask) == 5);
  }
  // the frames that are not delivered, each counted, each buffer (but the unknown one) posted again
  got.clear();
  fillRx(rx, 7, ip, 0, 0, false);                       // not done
  fillRx(rx, 8, ip, 0, 1u << 31);                       // an FCS error
  fillRx(rx, 9, ip, 0, kRxDescNullData);                // null data
  fillRx(rx, 10, ip, 0, 0, true, kRxDecapNativeWifi);   // not Ethernet
  reoEntry(dp, 2, rx.refillBus[7], 7, 300);
  reoEntry(dp, 3, rx.refillBus[8], 8, 300);
  reoEntry(dp, 4, rx.refillBus[9], 9, 300);
  reoEntry(dp, 5, rx.refillBus[10], 10, 300);
  reoEntry(dp, 6, rx.refillBus[11] + 4096, 11, 300);    // an address that is not the cookie's
  reoEntry(dp, 7, rx.refillBus[12], 12, 300, kDpMsduFirst | kDpMsduContinuation);
  reoEntry(dp, 8, dp.linkBus, 0, 0, 0, kDpReoBufTypeLinkDesc);
  *dp.reo.theirs = 9 * dp.reo.words;
  fillRx(rx, 12, ip, 0);
  CHECK(dpPoll(dp, io, deliver) == 7);
  CHECK(got.empty());
  CHECK(dp.st.rxNotDone == 1 && dp.st.rxErrors == 1 && dp.st.lastErrors == 1u << 31 && dp.st.rxNullData == 1);
  CHECK(dp.st.rxNotEthernet == 1 && dp.st.rxBadCookie == 1 && dp.st.rxMulti == 1 && dp.st.rxLinkDesc == 1);
  CHECK(dp.st.rxRecycled == 2 + 5);
  // the refill ring full: a buffer that comes back while there is no room is counted
  *refill.tail = refill.ours * refill.entryWords;       // the firmware has taken everything up to our head: all free
  CHECK(httRefillFree(rx) == refill.entries - 1);
  // the reorder ring wraps: entries 255 and 0 read in one turn
  {
    got.clear();
    dp.reo.ours = kDpReoEntries - 1;
    fillRx(rx, 14, ip, 0);
    fillRx(rx, 15, eapol, 0);
    reoEntry(dp, kDpReoEntries - 1, rx.refillBus[14], 14, uint32_t(ip.size()));
    reoEntry(dp, 0, rx.refillBus[15], 15, uint32_t(eapol.size()));
    *dp.reo.theirs = 1 * dp.reo.words;
    CHECK(dpPoll(dp, io, deliver) == 2);
    CHECK(got.size() == 2 && got[0].kind == kDpRxEthernet && got[1].kind == kDpRxEapol && dp.st.rxEapol == 2);
    CHECK(dp.reo.ours == 1 && chip.regs[kDpReo2Sw1R2 + 4] == 8);
  }
  // no room in the refill ring: the buffer is counted, not posted
  {
    *refill.tail = ((refill.ours + 1) % refill.entries) * refill.entryWords;   // the firmware has taken nothing new
    CHECK(httRefillFree(rx) == 0);
    fillRx(rx, 16, ip, 0);
    reoEntry(dp, 1, rx.refillBus[16], 16, uint32_t(ip.size()));
    *dp.reo.theirs = 2 * dp.reo.words;
    const uint32_t full = dp.st.rxRecycleFull;
    CHECK(dpPoll(dp, io, deliver) == 1);
    CHECK(dp.st.rxRecycleFull == full + 1);
    *refill.tail = refill.ours * refill.entryWords;
  }

  // ---- the release rings: a receive buffer back on WBM2SW3 is posted again; an unknown one is only counted
  {
    uint8_t *e = dp.rel3.va;
    put32(e, uint32_t(rx.refillBus[13]));
    put32(e + 4, (uint32_t(rx.refillBus[13] >> 32) & 0xffu) | kDpRbmSw1 << 8 | 13u << 12);
    put32(e + 8, kDpRelSrcRxdma | 4u << 19);   // released by the receive DMA, its error 4
    std::vector<uint8_t> group = ethFrame(0x0806, 50, 0x22);
    group[0] = 0xff;                          // a broadcast
    fillRx(rx, 13, group, 0, 1u << 28 | kRxDescMcbc);
    put32(e + 32, 0x12345678);   // the next entry: not a buffer of ours
    put32(e + 36, 0xffu << 12);
    put32(e + 40, kDpRelSrcReo | 1u << 24 | 7u << 26);
    *dp.rel3.theirs = 2 * dp.rel3.words;
    const uint32_t before = dp.st.rxRecycled;
    CHECK(dpPoll(dp, io, deliver) == 2);
    CHECK(dp.st.relEntries == 2 && dp.st.relRecycled == 1 && dp.st.relOther == 1 && dp.st.rxRecycled == before);
    // why: by source and code, and the first one read out of its buffer
    CHECK(dp.st.relBySource[kDpRelSrcRxdma] == 1 && dp.st.relRxdmaError[4] == 1 && dp.st.relBySource[kDpRelSrcReo] == 1 &&
          dp.st.relReoError[7] == 1 && dp.st.relGroup == 1 && dp.st.relUnicast == 0 && dp.st.relRecorded == 2);
    CHECK(dp.st.rel[0].descRead && dp.st.rel[0].groupAddressed && dp.st.rel[0].etherType == 0x0806 &&
          (dp.st.rel[0].info13 & (1u << 28)) && dp.st.rel[0].length == group.size());
    CHECK(!dp.st.rel[1].descRead && dp.st.rel[1].reoPush == 1 && dp.st.rel[1].reoError == 7);
    // boot 10g: a group frame the reorder unit released for want of a queue (push 0, error 0), decrypted and whole, is
    // delivered; one with a descriptor error is not
    got.clear();
    std::vector<uint8_t> arp = ethFrame(0x0806, 46, 0x33);
    arp[0] = 0xff;
    fillRx(rx, 20, arp, 2, kRxDescMcbc);
    fillRx(rx, 21, arp, 0, kRxDescMcbc | 1u << 29);
    uint8_t *f = dp.rel3.va + 2 * 32;
    put32(f, uint32_t(rx.refillBus[20]));
    put32(f + 4, (uint32_t(rx.refillBus[20] >> 32) & 0xffu) | kDpRbmSw1 << 8 | 20u << 12);
    put32(f + 8, kDpRelSrcReo);
    put32(f + 32, uint32_t(rx.refillBus[21]));
    put32(f + 36, (uint32_t(rx.refillBus[21] >> 32) & 0xffu) | kDpRbmSw1 << 8 | 21u << 12);
    put32(f + 40, kDpRelSrcReo);
    *dp.rel3.theirs = 4 * dp.rel3.words;
    const uint32_t frames = dp.st.rxFrames;
    CHECK(dpPoll(dp, io, deliver) == 2);
    CHECK(got.size() == 1 && got[0].kind == kDpRxEthernet && got[0].bytes == arp);
    CHECK(dp.st.relDelivered == 1 && dp.st.rxFrames == frames + 1 && dp.st.relRecycled == 3);
    CHECK(chip.regs[kDpWbm2Sw0R2 + 3 * 8 + 4] == 4 * 8);
  }
  // ---- the exception ring: counted, its push reason and error kept, passed over
  {
    uint8_t *e = dp.reoExc.va;
    put32(e + 28, 1u << kDpReoPushShift | 5u << kDpReoErrShift);
    *dp.reoExc.theirs = dp.reoExc.words;
    CHECK(dpPoll(dp, io, deliver) == 1);
    CHECK(dp.st.excEntries == 1 && dp.st.lastPushReason == 1 && dp.st.lastErrorCode == 5);
    CHECK(chip.regs[kDpReo2Sw0R2 + 4] == 8);
  }

  // ---- the peer map's search entry (the second and third forms) and the first form's none
  {
    HttRx h;
    uint8_t m[16] = {};
    put32(m, kHttT2hPeerMap2 | 1u << 8 | 2u << 16);
    put32(m + 4, uint32_t(kAp[0] | kAp[1] << 8 | kAp[2] << 16 | uint32_t(kAp[3]) << 24));
    put32(m + 8, uint32_t(kAp[4] | kAp[5] << 8) | 58u << 16);
    put32(m + 12, 0x0123);
    httReceive(h, m, 16);
    const HttPeerMap *p = httPeerMapOf(h, 1, kAp);
    CHECK(p && p->hasSearch && p->hwPeerId == 58 && p->astHash == 0x123 && p->peerId == 2);
    put32(m, kHttT2hPeerMap3 | 1u << 8 | 3u << 16);
    put32(m + 12, 61u | 0x0456u << 16);
    httReceive(h, m, 16);
    p = httPeerMapOf(h, 1, kAp);
    CHECK(p && p->hasSearch && p->hwPeerId == 61 && p->astHash == 0x456 && p->peerId == 3);
    put32(m, kHttT2hPeerMap | 1u << 8 | 4u << 16);
    httReceive(h, m, 12);
    p = httPeerMapOf(h, 1, kAp);
    CHECK(p && !p->hasSearch && p->peerId == 4);
  }

  // ---- the transmit side
  std::vector<uint8_t> out = ethFrame(kEtherTypeEapol, 121 - 14, 0x77);
  CHECK(!dpSend(dp, io, out.data(), uint32_t(out.size())) && dp.st.txNotReady == 1);
  HttPeerMap peer;
  peer.hasSearch = true;
  peer.hwPeerId = 58;
  peer.astHash = 0x123;
  dpTxSetupPeer(dp, io, 1, kDpPdevSingle, &peer);
  CHECK(dp.txReady);
  CHECK(chip.regs[kDpTclBankConfig] == 0x4a04u);
  CHECK(dpSend(dp, io, out.data(), uint32_t(out.size())));
  {
    const uint8_t *e = dp.tcl.va;
    CHECK(get32(e) == uint32_t(dp.tx[0].bus));
    CHECK(get32(e + 4) == ((uint32_t(dp.tx[0].bus >> 32) & 0xffu) | 5u << 8 | 0u << 12));
    CHECK(get32(e + 8) == 0);                                        // a buffer, bank 0
    CHECK(get32(e + 12) == (1u | 1u << 3 | 0u << 11) << 16);         // vdev based, vdev 1, radio 0
    CHECK(get32(e + 16) == 121);
    CHECK(get32(e + 20) == (1u | 0u << 4 | 1u << 24));               // TID overwritten (0), vdev 1
    CHECK(get32(e + 24) == (58u | 0x3u << 20));
    CHECK(get32(e + 28) == 0);
    CHECK(std::memcmp(dp.tx[0].va, out.data(), out.size()) == 0);
    CHECK(chip.regs[kDpTcl1R2] == 8);
    CHECK(dp.tx[0].busy && dp.st.txEapol == 1 && dp.st.txFrames == 1 && dp.st.txBytes == 121);
  }
  // its completion: acknowledged, the buffer free again, our tail moved
  {
    uint8_t *e = dp.txComp.va;
    put32(e, uint32_t(dp.tx[0].bus));
    put32(e + 4, (uint32_t(dp.tx[0].bus >> 32) & 0xffu) | 5u << 8 | 0u << 12);
    put32(e + 8, kDpRelSrcTqm | 0u << kDpTqmReasonShift);
    *dp.txComp.theirs = dp.txComp.words;
    CHECK(dpPoll(dp, io, deliver) == 1);
    CHECK(dp.st.txCompletions == 1 && dp.st.txAcked == 1 && !dp.tx[0].busy);
    CHECK(chip.regs[kDpWbm2Sw0R2 + 4] == 8);
  }
  // a frame not acknowledged (reason 2), one released by the firmware, one with a cookie that is not in flight
  {
    CHECK(dpSend(dp, io, out.data(), uint32_t(out.size())));   // buffer 0 again, slot 1
    uint8_t *e = dp.txComp.va + 8 * 4;
    put32(e, uint32_t(dp.tx[0].bus));
    put32(e + 4, (uint32_t(dp.tx[0].bus >> 32) & 0xffu) | 5u << 8);
    put32(e + 8, kDpRelSrcTqm | 2u << kDpTqmReasonShift);
    e += 32;
    put32(e, uint32_t(dp.tx[3].bus));
    put32(e + 4, (uint32_t(dp.tx[3].bus >> 32) & 0xffu) | 5u << 8 | 3u << 12);
    put32(e + 8, kDpRelSrcFw);
    *dp.txComp.theirs = 3 * dp.txComp.words;
    CHECK(dpPoll(dp, io, deliver) == 2);
    CHECK(dp.st.txNotAcked == 1 && dp.st.txFwReleased == 1 && dp.st.txBadCookie == 1);
    CHECK(dp.st.lastTxSource == kDpRelSrcFw);   // the last one seen
    CHECK(!dp.tx[0].busy);
  }
  // the limits: too short, too long, every buffer in flight
  CHECK(!dpSend(dp, io, out.data(), 10) && dp.st.txTooLong == 1);
  {
    std::vector<uint8_t> big(kDpTxBufferBytes + 1, 0);
    CHECK(!dpSend(dp, io, big.data(), uint32_t(big.size())) && dp.st.txTooLong == 2);
  }
  uint32_t sent = 0;
  while (dpSend(dp, io, out.data(), uint32_t(out.size()))) ++sent;
  CHECK(sent == kDpTxBuffers && dp.st.txNoBuffer == 1);
  // the TCL ring full before the buffers run out (the chip has read nothing: its tail stays where it was)
  {
    for (DpTxBuf &b : dp.tx) b.busy = false;
    *dp.tcl.theirs = dp.tcl.ours * dp.tcl.words;   // everything so far read
    uint32_t more = 0;
    for (uint32_t i = 0; i < 2 * kDpTclEntries && more < kDpTclEntries; ++i) {
      const uint32_t noBuffer = dp.st.txNoBuffer;
      if (!dpSend(dp, io, out.data(), uint32_t(out.size()))) {
        if (dp.st.txNoBuffer != noBuffer) {   // the buffers ran out first: the chip "completed" them all
          for (DpTxBuf &b : dp.tx) b.busy = false;
          continue;
        }
        break;
      }
      ++more;
    }
    CHECK(more == kDpTclEntries - 1 && dp.st.txRingFull == 1);
  }
  dpTxStop(dp);
  CHECK(!dpSend(dp, io, out.data(), uint32_t(out.size())));

  // ---- block by block (boot 10c's reset): the trace comes before each block's first access, and the owner may stop early
  {
    Arena a2;
    uint8_t *w2 = static_cast<uint8_t *>(std::aligned_alloc(1u << 20, 4u << 20));
    arenaInit(a2, w2, 0x2000'0000ull, 4u << 20);
    Dp d2;
    CHECK(dpPlan(d2, a2, &rx));
    Chip c2;
    ChipIo io2{&c2, chipRead, chipWrite};
    std::vector<std::pair<uint32_t, size_t>> traced;   // block, accesses before it
    dpProgramBlocks(d2, io2, kDpBlockReo, [&](uint32_t block) { traced.push_back({block, c2.writes.size()}); });
    CHECK(traced.size() == 4 && traced[0].first == kDpBlockProbe && traced[3].first == kDpBlockReo);
    CHECK(traced[0].second == 0 && traced[1].second == 0);   // block 0 only reads
    CHECK(!d2.programmed && d2.blocksDone == 4);
    CHECK(written(c2, kDpTcl1R0) && written(c2, kDpWbm2Sw0R0) && written(c2, kDpReo2Sw1R0));
    CHECK(!written(c2, kDpReo2Sw0R0) && !written(c2, kDpIdleLinkR0) && !written(c2, kDpReoDestIx2));
    // each block's first write is inside the range the trace names
    for (size_t i = 1; i < traced.size(); ++i) {
      const DpBlockRange g = dpBlockRange(d2, traced[i].first);
      const uint32_t first = c2.writes[traced[i].second].first;
      CHECK(first >= g.first && first <= g.last);
    }
    Dp d3;
    CHECK(dpPlan(d3, a2, &rx));
    Chip c3;
    ChipIo io3{&c3, chipRead, chipWrite};
    uint32_t calls = 0;
    dpProgramBlocks(d3, io3, kDpBlocks - 1, [&](uint32_t) { ++calls; });
    CHECK(calls == kDpBlocks && d3.programmed && d3.blocksDone == kDpBlocks && c3.regs[kDpReoDestIx3] == 0x11111111u);
    for (uint32_t b = 0; b < kDpBlocks; ++b) CHECK(dpBlockName(b)[0] != '?');
    std::free(w2);
  }

  // ---- a window too small for the data path: dpPlan says so
  {
    Arena tiny;
    std::vector<uint8_t> small(64 * 1024);
    arenaInit(tiny, small.data(), 0x8000'0000ull, uint32_t(small.size()));
    Dp none;
    CHECK(!dpPlan(none, tiny, &rx) && !none.planned);
  }
  std::free(window);
  if (failures) {
    std::printf("dp_host: %d failure(s)\n", failures);
    return 1;
  }
  std::printf("dp_host: all checks passed\n");
  return 0;
}
