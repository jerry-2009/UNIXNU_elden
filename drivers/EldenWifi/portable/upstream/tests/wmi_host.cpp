// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test of PianoWifi level 6: the copy engine (WifiCe.h), the host transport (WifiHtc.h), the firmware's message interface
// (WifiWmi.h) and the ladder that drives all three (WifiLink.h). What it holds the code to:
//   the copy engine: the rings and buffers out of the arena; the registers the driver programs (base and size, the descriptor
//             size, where the chip writes its own pointer, the largest buffer of a destination ring, the enable bit) read back
//             from a model of the chip's register space; a message sent and the completion that frees its buffer; a buffer
//             filled by the chip and the status entry that reports it; the one element a ring always leaves free; the rings
//             disabled by the teardown;
//   the transport: the firmware's ready message, a service connected and the endpoint its answer gives, set-up complete, the
//             credit accounting (a command costs credits, the firmware gives them back in a trailer), a refused service, a
//             header that does not fit its buffer, a trailer that does not fit its message;
//   the message interface: the initialisation command's TLVs (the fixed structure, the 72-word resource configuration with this
//             chip's own values, the empty memory-chunk array), the chip's capability and ready events, a station virtual
//             device with its two stream entries, a passive scan request (channel list, dwell times, the passive flag), the
//             scan's events and its management frames;
//   the scan list: a beacon's name and address, a hidden network, a probe answer, the same network twice (the stronger signal
//             kept), a frame that is not a scan result, a truncated frame, more networks than the list holds, and the masked
//             form of an address for a log line;
//   the faults: a firmware that refuses the service, one that asks for memory this level does not hand out, a scan that never
//             starts (the step times out), a scan that starts and never ends (the results stand and the teardown runs), an
//             event in the wrong step, and the teardown of a ladder that is given up on.
//   c++ -std=c++20 -Wall -Wextra -Werror -I.. wmi_host.cpp -o /tmp/wmi_host && /tmp/wmi_host
#include "WifiLink.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>

using namespace pianowifi;
static int failures;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

static constexpr uint64_t kBusBase = 0x20000000;        // the window's bus address, as piano-wifi-iova=1 gives it
static constexpr uint32_t kWindowBytes = 4u << 20;

static uint32_t get32(const uint8_t *at)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[i]) << (8 * i);
  return v;
}
static void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}

// ======================================================================== the chip: its register space and its copy engine
struct Device {
  std::vector<uint8_t> memory;                  // the DMA window as the chip sees it
  std::map<uint32_t, uint32_t> regs;            // the chip's register space above the window's start
  unsigned writes = 0, reads = 0;
  std::vector<std::pair<uint8_t, std::vector<uint8_t>>> toHost;   // (pipe, message) the firmware wants to send
  std::vector<std::pair<uint8_t, std::vector<uint8_t>>> fromHost; // what it has taken from the host
  bool stalled = false;                         // a chip that takes nothing (for the timeout tests)

  Device() : memory(kWindowBytes, 0) {}

  uint8_t *at(uint64_t bus, uint32_t bytes)
  {
    if (bus < kBusBase || bus + bytes > kBusBase + memory.size()) return nullptr;
    return memory.data() + (bus - kBusBase);
  }
  static uint32_t read(void *ctx, uint32_t address)
  {
    Device &d = *static_cast<Device *>(ctx);
    ++d.reads;
    return d.regs.count(address) ? d.regs[address] : 0;
  }
  static void write(void *ctx, uint32_t address, uint32_t value)
  {
    Device &d = *static_cast<Device *>(ctx);
    ++d.writes;
    d.regs[address] = value;
  }
  ChipIo io() { return ChipIo{this, &Device::read, &Device::write}; }

  // ---- one ring as the chip reads its registers ----
  struct Ring {
    uint64_t base = 0, pointer = 0;
    uint32_t entries = 0, words = 0, r2 = 0, ringId = 0;
    bool enabled = false;
    uint32_t own = 0;                           // the chip's own slot
  };
  Ring ring(uint32_t r0, uint32_t r2, bool hostProduces)
  {
    Ring r;
    const uint32_t msb = regs.count(r0 + kRingBaseMsb) ? regs[r0 + kRingBaseMsb] : 0;
    r.base = uint64_t(regs.count(r0) ? regs[r0] : 0) | uint64_t(msb & kRingBaseMsbAddrHi) << 32;
    const uint32_t sizeWords = (msb >> kRingBaseMsbSizeShift) & kRingBaseMsbSizeMask;
    const uint32_t id = regs.count(r0 + kRingId) ? regs[r0 + kRingId] : 0;
    r.words = id & kRingIdEntrySizeMask;
    r.ringId = (id >> kRingIdRingIdShift) & 0xffu;
    r.entries = r.words ? sizeWords / r.words : 0;
    const uint32_t lo = hostProduces ? kSrcRingTpAddrLo : kDstRingHpAddrLo;
    const uint32_t hi = hostProduces ? kSrcRingTpAddrHi : kDstRingHpAddrHi;
    r.pointer = uint64_t(regs.count(r0 + lo) ? regs[r0 + lo] : 0) | uint64_t(regs.count(r0 + hi) ? regs[r0 + hi] : 0) << 32;
    r.enabled = (regs.count(r0 + kRingMisc) ? regs[r0 + kRingMisc] : 0) & kRingMiscEnable;
    r.r2 = r2;
    return r;
  }
  uint32_t hostSlot(const Ring &r, uint32_t r2) { return r.words && regs.count(r2) ? (regs[r2] / r.words) % (r.entries ? r.entries : 1) : 0; }
  void putPointer(const Ring &r, uint32_t slot)
  {
    uint8_t *p = at(r.pointer, 4);
    if (p) put32(p, slot * r.words);
  }

  // What the chip does between two polls of the driver: take what the host put on the source rings, fill buffers with what the
  // firmware wants to send, and report each one in the destination-status ring.
  std::map<uint8_t, uint32_t> srcOwn, dstOwn, statusOwn;
  void run()
  {
    if (stalled) return;
    for (const CeHostPipe &want : kCeHostPipes) {
      const uint32_t srcUnit = kUnitCe0Src + want.pipe * kCeUnitStride;
      const uint32_t dstUnit = kUnitCe0Dst + want.pipe * kCeUnitStride;
      if (want.srcEntries) {
        Ring src = ring(srcUnit, srcUnit + kCeR2Hp, true);
        src.own = srcOwn[want.pipe];
        if (src.enabled && src.entries) {
          const uint32_t host = hostSlot(src, src.r2);
          while (src.own != host) {
            const uint8_t *desc = at(src.base + uint64_t(src.own) * src.words * 4, src.words * 4);
            if (desc) {
              const uint64_t address = uint64_t(get32(desc)) | uint64_t(get32(desc + 4) & kCeDescAddrHiMask) << 32;
              const uint32_t length = (get32(desc + 4) >> kCeDescLenShift) & kCeDescLenMask;
              const uint8_t *payload = at(address, length);
              if (payload) fromHost.push_back({want.pipe, std::vector<uint8_t>(payload, payload + length)});
            }
            src.own = (src.own + 1) % src.entries;
            srcOwn[want.pipe] = src.own;
            putPointer(src, src.own);
          }
        }
      }
      if (!want.dstEntries) continue;
      Ring dst = ring(dstUnit, dstUnit + kCeR2Hp, true);
      Ring status = ring(dstUnit + kCeStatusRingBase, dstUnit + kCeStatusR2Hp, false);
      dst.own = dstOwn[want.pipe];
      status.own = statusOwn[want.pipe];
      if (!dst.enabled || !status.enabled || !dst.entries) continue;
      const uint32_t hostDst = hostSlot(dst, dst.r2);
      while (!toHost.empty() && dst.own != hostDst) {
        if (toHost.front().first != want.pipe) break;
        const uint8_t *desc = at(dst.base + uint64_t(dst.own) * dst.words * 4, dst.words * 4);
        if (!desc) break;
        const uint64_t address = uint64_t(get32(desc)) | uint64_t(get32(desc + 4) & kCeDescAddrHiMask) << 32;
        std::vector<uint8_t> message = toHost.front().second;
        if (message.size() > want.bufferBytes) break;
        uint8_t *buffer = at(address, uint32_t(message.size()));
        if (!buffer) break;
        std::memcpy(buffer, message.data(), message.size());
        toHost.erase(toHost.begin());
        dst.own = (dst.own + 1) % dst.entries;
        dstOwn[want.pipe] = dst.own;
        putPointer(dst, dst.own);
        uint8_t *entry = at(status.base + uint64_t(status.own) * status.words * 4, status.words * 4);
        if (entry) {
          std::memset(entry, 0, status.words * 4);
          put32(entry, uint32_t(message.size()) << kCeStatusLenShift);
          put32(entry + 12, 0);
        }
        status.own = (status.own + 1) % status.entries;
        statusOwn[want.pipe] = status.own;
        putPointer(status, status.own);
      }
    }
  }
};

// ==================================================================================== the firmware above the copy engine
struct Firmware {
  Device *device = nullptr;
  uint32_t credits = 4, creditSize = 1024, endpoints = 8;
  uint8_t wmiEndpoint = 2;
  uint8_t mac[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x02};
  uint8_t extraMac[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x03};
  uint32_t extraMacs = 0;              // how many addresses the array behind the ready event carries
  // what it has seen, and what it checks
  bool readySent = false, connectSeen = false, setupSeen = false, initSeen = false, vdevSeen = false, scanSeen = false,
       stopSeen = false, deleteSeen = false;
  // the radio's set-up (P22): the hardware mode, the parameters and the channel list
  bool hwModeSeen = false, chanListSeen = false, answerHwMode = true, sendReg = true, regExtended = false;
  uint32_t hwModeIndex = 0, hwModePdev = 0, hwModeBands = 0, hwModeStatus = 0;
  uint32_t paramsSeen = 0, chanListCount = 0, chanListFlags = 0, chanListPdev = 0;
  std::vector<std::pair<uint32_t, uint32_t>> params;     // (parameter, value) in the order they arrived
  std::vector<std::pair<uint32_t, uint32_t>> chanEntries;   // (frequency, information word)
  std::vector<uint32_t> commandOrder;                    // every command identifier, in order
  std::vector<std::pair<uint32_t, uint32_t>> vdevParams;  // level 7's device parameters (the hand-off test)
  uint32_t initWords = 0, scanChannels = 0, scanFlags = 0, scanBssids = 0, scanSsids = 0, vdevStreams = 0, vdevType = 0;
  std::vector<uint32_t> channelList;
  uint8_t vdevMac[6] = {};
  uint32_t cfg[kWmiResourceConfigWords] = {};
  // what it does
  uint8_t connectStatus = 0;
  uint32_t memRequests = 0;
  bool answerScanStarted = true, answerScanCompleted = true, sendBeacons = true, badFrameLength = false,
       shortBeacon = false, manyNetworks = false, wrongStepEvent = false, sendExtended = true, badStatus = false;
  uint32_t creditsGivenBack = 0;
  // P23: the data interface, its rings as the firmware reads them from the set-up messages, and a radio that — like the chip
  // on the tablet — keeps no frame unless the host gave it receive buffers (rxNeedsRings).
  uint8_t httEndpoint = 1;
  bool httConnectSeen = false, httVersionSeen = false, rxNeedsRings = true, answerStats = true, answerHtt = true;
  uint32_t scanIdSeen = kWmiScanId, scansSeen = 0;
  uint32_t httOption = 0, statsRequests = 0, framesDelivered = 0, framesDropped = 0, statusTaken = 0, chanInfoSent = 0;
  struct Ring {
    bool seen = false;
    uint32_t kind = 0, htt = 0, radio = 0, sizeWords = 0, entryWords = 0, flags = 0;
    uint64_t base = 0, head = 0, tail = 0;
  };
  std::vector<Ring> rings;
  uint32_t srngSeen = 0, refillRbm = 0xff, refillCookieMax = 0;

  Ring *ringOf(uint32_t htt, uint32_t radio)
  {
    for (Ring &r : rings)
      if (r.htt == htt && r.radio == radio) return &r;
    return nullptr;
  }
  uint32_t word(uint64_t bus)
  {
    const uint8_t *at = device->at(bus, 4);
    return at ? get32(at) : 0;
  }
  void setWord(uint64_t bus, uint32_t v)
  {
    uint8_t *at = device->at(bus, 4);
    if (at) put32(at, v);
  }
  // One receive buffer taken from the refill ring, as the firmware does before the receive DMA can write a frame: false when
  // the host gave none (or none is left). The entry must name a buffer inside the window and the manager the host chose.
  bool takeRefillBuffer()
  {
    Ring *refill = ringOf(kHttRingHost1ToFwRxbuf, 0);
    if (!refill || !refill->entryWords) return false;
    const uint32_t head = word(refill->head), tail = word(refill->tail);
    if (head == tail) return false;
    const uint8_t *entry = device->at(refill->base + uint64_t(tail) * 4, 8);
    if (!entry) return false;
    const uint64_t bus = uint64_t(get32(entry)) | uint64_t(get32(entry + 4) & kRxBufAddrHiMask) << 32;
    CHECK(device->at(bus, kRxBufferBytes) != nullptr);
    refillRbm = (get32(entry + 4) >> kRxBufRbmShift) & 0xfu;
    const uint32_t cookie = get32(entry + 4) >> kRxBufCookieShift;
    if (cookie > refillCookieMax) refillCookieMax = cookie;
    setWord(refill->tail, (tail + refill->entryWords) % refill->sizeWords);
    return true;
  }
  // One status buffer of a radio taken by the receive DMA (its tail moved), as the hardware does for every PPDU it receives.
  void takeStatusBuffer(uint32_t radio)
  {
    Ring *status = ringOf(kHttRingRxdmaMonitorStatus, radio + 1);
    if (!status || !status->entryWords) return;
    const uint32_t head = word(status->head), tail = word(status->tail);
    if (head == tail) return;
    setWord(status->tail, (tail + status->entryWords) % status->sizeWords);
    ++statusTaken;
  }
  // An error entry from the receive DMA (its head moved), which the host must give back by moving its tail.
  void pushError()
  {
    Ring *errors = ringOf(kHttRingRxdmaNonMonitorDest, 1);
    if (!errors || !errors->entryWords) return;
    const uint32_t head = word(errors->head);
    setWord(errors->head, (head + errors->entryWords) % errors->sizeWords);
  }

  // A message to the host (on pipe 2, or pipe 1 for the data interface), with the transport's header and (for the message
  // interface's endpoint) a credit report.
  void toHost(uint8_t endpoint, const uint8_t *payload, uint32_t length, bool giveCredit, uint8_t pipe = 2)
  {
    std::vector<uint8_t> message(kHtcHeaderBytes + length, 0);
    const uint32_t trailerBytes = giveCredit ? kHtcRecordHeaderBytes + kHtcCreditReportBytes : 0;
    if (trailerBytes) message.resize(kHtcHeaderBytes + length + trailerBytes, 0);
    if (length) std::memcpy(message.data() + kHtcHeaderBytes, payload, length);
    if (trailerBytes) {
      uint8_t *trailer = message.data() + kHtcHeaderBytes + length;
      trailer[0] = kHtcRecordCredits;
      trailer[1] = kHtcCreditReportBytes;
      trailer[kHtcRecordHeaderBytes] = wmiEndpoint;
      trailer[kHtcRecordHeaderBytes + 1] = 1;
      ++creditsGivenBack;
    }
    const uint32_t payloadLength = length + trailerBytes;
    put32(message.data(), uint32_t(endpoint) | (trailerBytes ? uint32_t(kHtcFlagTrailerPresent) << kHtcHdrFlagsShift : 0u) |
                              (payloadLength & 0xffffu) << kHtcHdrLengthShift);
    put32(message.data() + 4, trailerBytes & 0xffu);
    device->toHost.push_back({pipe, message});
  }

  void sendReady()
  {
    uint8_t payload[12] = {};
    put32(payload, uint32_t(kHtcMsgReady) | credits << kHtcReadyCreditCountShift);
    put32(payload + 4, creditSize | endpoints << kHtcReadyEndpointsShift);
    put32(payload + 8, 1u | 1u << 8);
    toHost(0, payload, sizeof payload, false);
    readySent = true;
  }

  void onControl(const uint8_t *payload, uint32_t length)
  {
    CHECK(length >= 8);
    const uint32_t word0 = get32(payload);
    const uint16_t id = uint16_t(word0 & kHtcMsgIdMask);
    if (id == kHtcMsgConnectService) {
      const uint16_t service = uint16_t(word0 >> kHtcServiceShift);
      const uint32_t flags = get32(payload + 4);
      uint8_t answer[12] = {};
      put32(answer, uint32_t(kHtcMsgConnectServiceResp) | uint32_t(service) << kHtcServiceShift);
      if (service == kSvcHttData) {
        // The data interface, which must come before the message interface: no credit flow control, no credits.
        httConnectSeen = true;
        CHECK(!connectSeen);
        CHECK((flags & kHtcConnFlagDisableCreditFlow) != 0);
        CHECK(((flags >> kHtcConnRecvAllocShift) & 0xffu) == 0);
        put32(answer + 4, uint32_t(answerHtt ? 0 : 1) | uint32_t(httEndpoint) << kHtcRespEndpointShift |
                              uint32_t(256) << kHtcRespMaxMessageShift);
        toHost(0, answer, sizeof answer, false);
        return;
      }
      connectSeen = true;
      CHECK(service == kSvcWmiControl);
      CHECK((flags & kHtcConnFlagDisableCreditFlow) == 0);   // the message interface keeps credit flow control
      put32(answer + 4, uint32_t(connectStatus) | uint32_t(wmiEndpoint) << kHtcRespEndpointShift |
                            uint32_t(2048) << kHtcRespMaxMessageShift);
      toHost(0, answer, sizeof answer, false);
      return;
    }
    if (id == kHtcMsgSetupCompleteEx) {
      setupSeen = true;
      sendServiceReady();
      return;
    }
    CHECK(false);   // a control message this firmware does not know
  }

  void event(uint32_t id, const uint8_t *tlvs, uint32_t length)
  {
    std::vector<uint8_t> message(kWmiCmdHeaderBytes + length, 0);
    put32(message.data(), id & kWmiCmdIdMask);
    if (length) std::memcpy(message.data() + kWmiCmdHeaderBytes, tlvs, length);
    toHost(wmiEndpoint, message.data(), uint32_t(message.size()), true);
  }

  void sendServiceReady()
  {
    uint8_t buffer[256] = {};
    uint8_t *at = buffer;
    const uint32_t words = 32;
    put32(at, (words * 4) | uint32_t(kWmiTagServiceReadyEvent) << kWmiTlvTagShift);
    put32(at + 4 + 4 * 9, 2);            // two radio chains
    put32(at + 4 + 4 * 10, 0x11);        // the high-throughput capability
    put32(at + 4 + 4 * 15, 0x5);         // the system capability
    put32(at + 4 + 4 * 18, memRequests); // how much memory it wants
    put32(at + 4 + 4 * 19, 32);          // the channels it can scan
    put32(at + 4 + 4 * 20, 0x21);        // the board identifier
    put32(at + 4 + 4 * 26, 1);
    put32(at + 4 + 4 * 29, 3);           // the chain mask
    at += 4 + words * 4;
    put32(at, 16u | uint32_t(kWmiTagArrayUint32) << kWmiTlvTagShift);
    put32(at + 4, 0x1);
    at += 4 + 16;
    event(kWmiEvtServiceReady, buffer, uint32_t(at - buffer));
    if (!sendExtended) return;
    // What the firmware really sends behind it, and what its own host waits for before the initialisation.
    uint8_t ext[32] = {};
    put32(ext, 16u | uint32_t(kWmiTagServiceReadyExtEvent) << kWmiTlvTagShift);
    event(kWmiEvtServiceReadyExt, ext, 4 + 16);
    put32(ext, 16u | uint32_t(kWmiTagServiceReadyExt2Event) << kWmiTlvTagShift);
    event(kWmiEvtServiceReadyExt2, ext, 4 + 16);
  }

  void sendReadyEvent()
  {
    uint8_t buffer[256] = {};
    const uint32_t words = 15;
    put32(buffer, (words * 4) | uint32_t(kWmiTagReadyEvent) << kWmiTlvTagShift);
    std::memcpy(buffer + 4 + 24, mac, 6);
    put32(buffer + 4 + 4 * 8, 0);        // status: the firmware came up
    put32(buffer + 4 + 4 * 10, extraMacs);
    put32(buffer + 4 + 4 * 11, 16);      // the peers it has room for
    uint32_t length = 4 + words * 4;
    if (extraMacs) {   // the array of addresses behind it, as the chip on the tablet sends one (P22)
      put32(buffer + length, (extraMacs * 8) | uint32_t(kWmiTagArrayFixedStruct) << kWmiTlvTagShift);
      std::memcpy(buffer + length + 4, extraMac, 6);
      length += 4 + extraMacs * 8;
    }
    event(kWmiEvtReady, buffer, length);
    if (sendReg) sendRegEvent();
  }

  // The firmware's regulatory domain, which it sends by itself after the initialisation: fourteen words and then its rules,
  // each an own-header structure of three words (four in the extended form).
  void sendRegEvent()
  {
    uint8_t buffer[512] = {};
    const uint32_t words = regExtended ? kRegExtEventWords : kRegEventWords;
    const uint32_t ruleWords = regExtended ? kRegRuleExtWords : kRegRuleWords;
    const uint32_t tag = regExtended ? uint32_t(kWmiTagRegChanListCcExtEvent) : uint32_t(kWmiTagRegChanListCcEvent);
    put32(buffer, (words * 4) | tag << kWmiTlvTagShift);
    put32(buffer + 4 + 4 * 2, uint32_t('C') | uint32_t('N') << 8);   // the country, two characters
    put32(buffer + 4 + 4 * 3, 1);                                    // one radio
    put32(buffer + 4 + 4 * 6, 2);                                    // its radar region
    put32(buffer + 4 + 4 * 8, 20);
    put32(buffer + 4 + 4 * 9, 40);
    put32(buffer + 4 + 4 * 10, 20);
    put32(buffer + 4 + 4 * 11, 80);
    put32(buffer + 4 + 4 * 12, 1);                                   // one rule of the 2.4 GHz band
    put32(buffer + 4 + 4 * 13, 2);                                   // two of the 5 GHz band
    uint32_t length = 4 + words * 4;
    const uint32_t stride = 4 + ruleWords * 4;
    put32(buffer + length, (3 * stride) | uint32_t(kWmiTagArrayStruct) << kWmiTlvTagShift);
    length += 4;
    struct Rule { uint32_t start, end, bw, power, flags; };
    // 2412-2472 the whole lower band; 5170-5250 of the upper one; 5250-5330 with radar detection (passive).
    const Rule rules[3] = {{2402, 2482, 40, 20, 0}, {5170, 5250, 80, 23, 0}, {5250, 5330, 80, 23, kRegRuleFlagRadar}};
    for (unsigned i = 0; i < 3; ++i) {
      uint8_t *at = buffer + length + i * stride;
      put32(at, (ruleWords * 4) | uint32_t(regExtended ? kWmiTagRegRuleExt : kWmiTagRegRule) << kWmiTlvTagShift);
      put32(at + 4, rules[i].start | rules[i].end << 16);
      put32(at + 8, rules[i].bw | rules[i].power << 16);
      put32(at + 12, rules[i].flags);
    }
    length += 3 * stride;
    event(regExtended ? kWmiEvtRegChanListCcExt : kWmiEvtRegChanListCc, buffer, length);
  }

  void sendScanEvent(uint32_t type, uint32_t reason, uint32_t freq)
  {
    uint8_t buffer[64] = {};
    const uint32_t words = 7;
    put32(buffer, (words * 4) | uint32_t(kWmiTagScanEvent) << kWmiTlvTagShift);
    put32(buffer + 4, type);
    put32(buffer + 8, reason);
    put32(buffer + 12, freq);
    put32(buffer + 16, kWmiScanRequestorId);
    put32(buffer + 20, scanIdSeen);
    put32(buffer + 24, 0);
    event(kWmiEvtScan, buffer, 4 + words * 4);
  }

  // A beacon (or a probe answer) as the firmware hands it over: the header with the channel and the signal strength, then the
  // frame itself. A radio that needs the host's receive buffers keeps none without them (P23).
  void sendBeacon(const char *ssid, const uint8_t *bssid, uint32_t freq, int32_t rssi, uint8_t channel, bool probe,
                  bool truncate = false)
  {
    if (rxNeedsRings && !takeRefillBuffer()) {
      ++framesDropped;
      return;
    }
    ++framesDelivered;
    std::vector<uint8_t> frame;
    const uint32_t ssidLength = ssid ? uint32_t(std::strlen(ssid)) : 0;
    frame.resize(kDot11HeaderBytes + kDot11BeaconFixedBytes + 2 + ssidLength + 3, 0);
    frame[0] = uint8_t(probe ? kDot11SubtypeProbeResponse : kDot11SubtypeBeacon);
    std::memcpy(frame.data() + 16, bssid, 6);                  // the third address: the network's own
    frame[kDot11HeaderBytes + 10] = 0x11;                      // the capability, low byte
    uint32_t at = kDot11HeaderBytes + kDot11BeaconFixedBytes;
    frame[at] = kDot11ElementSsid;
    frame[at + 1] = uint8_t(ssidLength);
    if (ssidLength) std::memcpy(frame.data() + at + 2, ssid, ssidLength);
    at += 2 + ssidLength;
    frame[at] = kDot11ElementDsParams;
    frame[at + 1] = 1;
    frame[at + 2] = channel;
    if (truncate) frame.resize(kDot11HeaderBytes + 4);         // a frame that ends in the middle of its body
    uint8_t buffer[512] = {};
    const uint32_t words = 17;
    put32(buffer, (words * 4) | uint32_t(kWmiTagMgmtRxHeader) << kWmiTlvTagShift);
    put32(buffer + 4 + 4 * 0, channel);
    put32(buffer + 4 + 4 * 1, uint32_t(rssi - kNoiseFloorDbm));   // the ratio the firmware reports, not the strength
    put32(buffer + 4 + 4 * 4, badFrameLength ? uint32_t(frame.size() + 64) : uint32_t(frame.size()));
    put32(buffer + 4 + 4 * 5, badStatus ? uint32_t(kWmiRxStatusErrCrc) : 0u);
    put32(buffer + 4 + 4 * 11, uint32_t(rssi));
    put32(buffer + 4 + 4 * 16, freq);
    uint32_t length = 4 + words * 4;
    put32(buffer + length, uint32_t(frame.size()) | uint32_t(kWmiTagArrayByte) << kWmiTlvTagShift);
    std::memcpy(buffer + length + 4, frame.data(), frame.size());
    length += 4 + ((uint32_t(frame.size()) + 3u) & ~3u);
    event(kWmiEvtMgmtRx, buffer, length);
  }

  // The channel-information events of one visit: its start, then its end with the counters (the radio hears the air whether
  // or not it has buffers: the counters are not zero either way, which is what tells "no buffers" from "a deaf radio").
  void sendChanInfo(uint32_t freq, bool end)
  {
    uint8_t buffer[96] = {};
    put32(buffer, (14 * 4) | uint32_t(kWmiTagChanInfoEvent) << kWmiTlvTagShift);
    put32(buffer + 4 + 4 * 1, freq);
    put32(buffer + 4 + 4 * 2, end ? 1u : 0u);
    put32(buffer + 4 + 4 * 3, uint32_t(-96));
    put32(buffer + 4 + 4 * 4, end ? 4000u : 0u);
    put32(buffer + 4 + 4 * 5, end ? 10000u : 0u);
    put32(buffer + 4 + 4 * 8, end ? 1500u : 0u);
    put32(buffer + 4 + 4 * 12, 160);
    event(kWmiEvtChanInfo, buffer, 4 + 14 * 4);
    ++chanInfoSent;
  }

  void runScan()
  {
    if (answerScanStarted) sendScanEvent(kWmiScanEvStarted, 0, 2412);
    for (uint32_t freq : channelList) {
      sendChanInfo(freq, false);
      takeStatusBuffer(0);
      sendChanInfo(freq, true);
    }
    if (ringOf(kHttRingRxdmaNonMonitorDest, 1)) pushError();
    if (sendBeacons) {
      const uint8_t one[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
      const uint8_t two[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x66};
      const uint8_t three[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x77};
      sendBeacon("piano-test", one, 2437, -42, 6, false, shortBeacon);
      sendBeacon("piano-test", one, 2437, -30, 6, false, shortBeacon);   // the same network, a stronger signal
      sendBeacon(nullptr, two, 5180, -70, 36, false);                    // a network that does not say its name
      sendBeacon("piano-probe", three, 2462, -55, 11, true);             // a probe answer
      if (manyNetworks)
        for (unsigned i = 0; i < kScanEntriesMax + 4; ++i) {
          const uint8_t other[6] = {0x02, 0x11, 0x22, 0x33, 0x55, uint8_t(i)};
          sendBeacon("piano-many", other, 2412, -80, 1, false);
        }
    }
    if (wrongStepEvent) sendReadyEvent();   // a ready event long after the step that waits for one
    if (answerScanCompleted) sendScanEvent(kWmiScanEvCompleted, kWmiScanReasonCompleted, 0);
  }

  void onCommand(const uint8_t *payload, uint32_t length)
  {
    CHECK(length >= kWmiCmdHeaderBytes);
    const uint32_t id = get32(payload) & kWmiCmdIdMask;
    const uint8_t *tlvs = payload + kWmiCmdHeaderBytes;
    const uint32_t left = length - kWmiCmdHeaderBytes;
    commandOrder.push_back(id);
    switch (id) {
    case kWmiCmdPdevSetHwMode: {
      hwModeSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagPdevSetHwModeCmd, &size);
      CHECK(cmd && size == 3 * 4);
      if (!cmd) return;
      hwModePdev = wmiGet(cmd, 0);
      hwModeIndex = wmiGet(cmd, 1);
      hwModeBands = wmiGet(cmd, 2);
      if (!answerHwMode) return;
      uint8_t buffer[64] = {};
      put32(buffer, (6 * 4) | uint32_t(kWmiTagPdevSetHwModeResp) << kWmiTlvTagShift);
      put32(buffer + 4, hwModeStatus);
      event(kWmiEvtPdevSetHwModeResp, buffer, 4 + 6 * 4);
      return;
    }
    case kWmiCmdPdevSetParam: {
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagPdevSetParamCmd, &size);
      CHECK(cmd && size == 3 * 4);
      if (!cmd) return;
      CHECK(wmiGet(cmd, 0) == kWmiPdevIdSoc);
      params.push_back({wmiGet(cmd, 1), wmiGet(cmd, 2)});
      ++paramsSeen;
      return;
    }
    case kWmiCmdRequestStats: {
      ++statsRequests;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagRequestStatsCmd, &size);
      CHECK(cmd && size == 5 * 4);
      if (!cmd) return;
      CHECK(wmiGet(cmd, 0) == kWmiStatsPdev && wmiGet(cmd, 4) == kWmiPdevIdSoc);
      if (!answerStats) return;
      // the fixed structure, then one radio record in a byte array
      std::vector<uint8_t> buffer(4 + kWmiStatsEventWords * 4 + 4 + kWmiPdevStatsWords * 4, 0);
      put32(buffer.data(), (kWmiStatsEventWords * 4) | uint32_t(kWmiTagStatsEvent) << kWmiTlvTagShift);
      put32(buffer.data() + 4 + 4 * 0, kWmiStatsPdev);
      put32(buffer.data() + 4 + 4 * 1, 1);
      uint8_t *array = buffer.data() + 4 + kWmiStatsEventWords * 4;
      put32(array, (kWmiPdevStatsWords * 4) | uint32_t(kWmiTagArrayByte) << kWmiTlvTagShift);
      uint8_t *record = array + 4;
      put32(record + 4 * 0, uint32_t(-96));
      put32(record + 4 * 2, 30000);            // receiving cycles: the radio hears
      put32(record + 4 * 3, 80000);
      put32(record + 4 * 4, 200000);
      uint8_t *rx = record + kWmiPdevStatsRxAt * 4;
      put32(rx + 4 * 1, 40 + framesDelivered);  // statuses received
      put32(rx + 4 * 9, framesDelivered);       // MPDUs delivered to the firmware itself
      put32(rx + 4 * 13, framesDropped);        // MPDU errors
      event(kWmiEvtUpdateStats, buffer.data(), uint32_t(buffer.size()));
      return;
    }
    case kWmiCmdScanChanList: {
      chanListSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagScanChanListCmd, &size);
      CHECK(cmd && size == 3 * 4);
      if (!cmd) return;
      chanListCount = wmiGet(cmd, 0);
      chanListFlags = wmiGet(cmd, 1);
      chanListPdev = wmiGet(cmd, 2);
      uint32_t arraySize = 0;
      const uint8_t *array = wmiFind(tlvs, left, kWmiTagArrayStruct, &arraySize);
      const uint32_t stride = kWmiTlvHeaderBytes + kWmiChannelWords * 4;
      CHECK(array && arraySize == chanListCount * stride);
      chanEntries.clear();
      if (array)
        for (uint32_t i = 0; i < chanListCount; ++i) {
          const uint8_t *at = array + i * stride;
          CHECK((get32(at) >> kWmiTlvTagShift) == uint32_t(kWmiTagChannel));
          CHECK((get32(at) & kWmiTlvLenMask) == kWmiChannelWords * 4);
          const uint8_t *fields = at + kWmiTlvHeaderBytes;
          CHECK(wmiGet(fields, 1) == wmiGet(fields, 0));   // a 20 MHz channel is its own centre frequency
          chanEntries.push_back({wmiGet(fields, 0), wmiGet(fields, 3)});
        }
      return;
    }
    case kWmiCmdInit: {
      initSeen = true;
      uint32_t size = 0;
      const uint8_t *fixed = wmiFind(tlvs, left, kWmiTagInitCmd, &size);
      CHECK(fixed && size == 7 * 4);
      CHECK(fixed && wmiGet(fixed, 6) == 0);        // no memory chunks
      const uint8_t *cfgTlv = wmiFind(tlvs, left, kWmiTagResourceConfig, &size);
      CHECK(cfgTlv && size == kWmiResourceConfigWords * 4);
      initWords = size / 4;
      if (cfgTlv)
        for (uint32_t i = 0; i < initWords && i < kWmiResourceConfigWords; ++i) cfg[i] = wmiGet(cfgTlv, i);
      const uint8_t *chunks = wmiFind(tlvs, left, kWmiTagArrayStruct, &size);
      CHECK(chunks && size == 0);
      sendReadyEvent();
      return;
    }
    case kWmiCmdVdevCreate: {
      vdevSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagVdevCreateCmd, &size);
      CHECK(cmd && size == 11 * 4);
      if (!cmd) return;
      CHECK(wmiGet(cmd, 0) == 0);
      vdevType = wmiGet(cmd, 1);
      std::memcpy(vdevMac, cmd + 12, 6);
      // No firmware of this family is ever given an all-zero device address (P22, docs section 10.27).
      CHECK(vdevMac[0] || vdevMac[1] || vdevMac[2] || vdevMac[3] || vdevMac[4] || vdevMac[5]);
      vdevStreams = wmiGet(cmd, 5);
      CHECK(wmiGet(cmd, 6) == kWmiPdevIdSoc);
      const uint8_t *array = wmiFind(tlvs, left, kWmiTagArrayStruct, &size);
      CHECK(array && size == kWmiBandCount * 16);
      if (array)
        for (uint32_t band = 0; band < kWmiBandCount; ++band) {
          const uint8_t *entry = array + band * 16;
          CHECK((get32(entry) >> kWmiTlvTagShift) == uint32_t(kWmiTagVdevTxrxStreams));
          CHECK((get32(entry) & kWmiTlvLenMask) == 12);
          CHECK(wmiGet(entry + 4, 0) == band);
        }
      return;
    }
    case kWmiCmdStartScan: {
      scanSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagStartScanCmd, &size);
      CHECK(cmd && size == kWmiStartScanWords * 4);
      if (!cmd) return;
      scanIdSeen = wmiGet(cmd, 0);
      ++scansSeen;
      CHECK(scanIdSeen == kWmiScanId || scanIdSeen == kWmiScanId + 2);   // the second round has its own identifier (P23)
      CHECK(wmiGet(cmd, 1) == kWmiScanRequestorId);
      CHECK(wmiGet(cmd, 2) == 0);
      CHECK(wmiGet(cmd, 5) == kWmiScanDwellActiveMs && wmiGet(cmd, 6) == kWmiScanDwellPassiveMs);
      CHECK(wmiGet(cmd, 12) == kWmiScanMaxTimeMs);
      CHECK(wmiGet(cmd, 3) == kWmiScanPriorityZero);
      CHECK(wmiGet(cmd, 35) == kWmiScanDwellActive2GhzMs && wmiGet(cmd, 36) == kWmiScanDwell6GhzMs);
      CHECK(wmiGet(cmd, 37) == kWmiScanDwell6GhzMs);
      scanFlags = wmiGet(cmd, 14);
      scanChannels = wmiGet(cmd, 16);
      scanBssids = wmiGet(cmd, 17);
      scanSsids = wmiGet(cmd, 18);
      const uint8_t *channels = wmiFind(tlvs, left, kWmiTagArrayUint32, &size);
      CHECK(channels && size == scanChannels * 4);
      channelList.clear();
      if (channels)
        for (uint32_t i = 0; i < scanChannels; ++i) channelList.push_back(wmiGet(channels, i));
      const uint8_t *bssid = wmiFind(tlvs, left, kWmiTagArrayFixedStruct, &size);
      CHECK(bssid && size == 0);   // the first such array is the list of names, which is empty
      runScan();
      return;
    }
    case kWmiCmdStopScan: {
      stopSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagStopScanCmd, &size);
      CHECK(cmd && size == 5 * 4);
      if (cmd) CHECK(wmiGet(cmd, 1) == scanIdSeen && wmiGet(cmd, 2) == kWmiStopScanOne);
      if (cmd) CHECK(wmiGet(cmd, 0) == 0 && wmiGet(cmd, 3) == 0 && wmiGet(cmd, 4) == kWmiPdevIdSoc);
      sendScanEvent(kWmiScanEvCompleted, kWmiScanReasonCancelled, 0);
      return;
    }
    case kWmiCmdVdevSetParam: {   // level 7's (the hand-off test sends one through linkSendWmi)
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagVdevSetParamCmd, &size);
      CHECK(cmd && size == 3 * 4);
      if (cmd) vdevParams.push_back({wmiGet(cmd, 1), wmiGet(cmd, 2)});
      return;
    }
    case kWmiCmdVdevDelete: {
      deleteSeen = true;
      uint32_t size = 0;
      const uint8_t *cmd = wmiFind(tlvs, left, kWmiTagVdevDeleteCmd, &size);
      CHECK(cmd && size == 4);
      return;
    }
    default:
      CHECK(false);   // a command this firmware does not know
      return;
    }
  }

  // The data interface's messages: the version request answered on pipe 1, a ring's set-up read the way the firmware reads it.
  void onHtt(const uint8_t *payload, uint32_t length)
  {
    CHECK(length >= 4);
    const uint32_t type = get32(payload) & 0xffu;
    if (type == kHttMsgVersionReq) {
      CHECK(length == 8);
      httVersionSeen = true;
      httOption = get32(payload + 4);
      uint8_t answer[8] = {};
      put32(answer, kHttT2hVersionConf | 0x1u << 8 | kHttVersionMajor << 16);
      toHost(httEndpoint, answer, 4, false, 1);
      return;
    }
    if (type == kHttMsgSrngSetup) {
      CHECK(length == kHttSrngSetupWords * 4);
      ++srngSeen;
      Ring r;
      r.seen = true;
      const uint32_t w0 = get32(payload);
      r.radio = (w0 >> 8) & 0xffu;
      r.htt = (w0 >> 16) & 0xffu;
      r.kind = (w0 >> 24) & 0xffu;
      r.base = uint64_t(get32(payload + 4)) | uint64_t(get32(payload + 8)) << 32;
      const uint32_t w3 = get32(payload + 12);
      r.sizeWords = w3 & 0xffffu;
      r.entryWords = (w3 >> 16) & 0xffu;
      r.flags = w3 & ~0xffffffu;
      r.head = uint64_t(get32(payload + 16)) | uint64_t(get32(payload + 20)) << 32;
      r.tail = uint64_t(get32(payload + 24)) | uint64_t(get32(payload + 28)) << 32;
      // what the firmware would check before it programs anything: everything inside the window, whole entries
      CHECK(r.entryWords && r.sizeWords % r.entryWords == 0);
      CHECK(device->at(r.base, r.sizeWords * 4) != nullptr);
      CHECK(device->at(r.head, 4) != nullptr && device->at(r.tail, 4) != nullptr);
      CHECK((r.kind == kHttSwToHw) == ((r.flags & kHttSrngLoopCountDisable) != 0));
      for (unsigned i = 8; i < kHttSrngSetupWords; ++i) CHECK(get32(payload + 4 * i) == 0);   // no MSI, no interrupts
      rings.push_back(r);
      return;
    }
    CHECK(false);   // a data-interface message this firmware does not know
  }

  // Everything the chip took from the host this turn.
  void drain()
  {
    while (!device->fromHost.empty()) {
      const std::vector<uint8_t> message = device->fromHost.front().second;
      device->fromHost.erase(device->fromHost.begin());
      CHECK(message.size() >= kHtcHeaderBytes);
      const uint32_t word0 = get32(message.data());
      const uint8_t endpoint = uint8_t(word0 & kHtcHdrEndpointMask);
      const uint32_t payload = (word0 >> kHtcHdrLengthShift) & 0xffffu;
      CHECK(payload + kHtcHeaderBytes <= message.size());
      if (endpoint == 0) {
        onControl(message.data() + kHtcHeaderBytes, payload);
      } else if (endpoint == httEndpoint && httConnectSeen) {
        CHECK(device->fromHost.empty() || true);
        onHtt(message.data() + kHtcHeaderBytes, payload);
      } else if (endpoint == wmiEndpoint) {
        onCommand(message.data() + kHtcHeaderBytes, payload);
        // The credit the firmware gives back when it has taken a message out of one of its receive buffers: without it a
        // host that sends several commands in a row (the radio's set-up of P22) would run out of credits.
        if ((word0 >> kHtcHdrFlagsShift) & kHtcFlagNeedCreditUpdate) toHost(wmiEndpoint, nullptr, 0, true);
      } else {
        CHECK(false);
      }
    }
  }
};

// ========================================================================================= the driver's side of the test
struct Host {
  Device device;
  Arena arena;
  Ce ce;
  HttRx htt;
  bool hasHtt = false;
  Link link;
  Firmware firmware;
  uint64_t now = 1000;
  std::vector<std::pair<int, std::string>> steps;

  static void note(void *ctx, int step, const char *what)
  {
    Host &h = *static_cast<Host *>(ctx);
    h.steps.push_back({step, what});
  }

  // The receive rings, planned and filled the way the kext does it when piano-wifi-l6pre asks for them (P23); withHtt=false
  // is the level 6 of the first two tablet boots (four pipes, no rings).
  bool start(bool withHtt = true, bool rbmSw1 = false)
  {
    arenaInit(arena, device.memory.data(), kBusBase, uint32_t(device.memory.size()));
    if (!cePlan(ce, arena, withHtt ? kCePipeMaskWithHtt : kCePipeMaskLevel6)) return false;
    ceProgram(ce, device.io());
    for (unsigned i = 0; i < kCeHostPipeCount; ++i) cePostRx(ce, device.io(), i);
    hasHtt = withHtt && httPlan(htt, arena, rbmSw1);
    if (hasHtt) httFill(htt);
    firmware.device = &device;
    link.note = &Host::note;
    link.noteCtx = this;
    return withHtt ? hasHtt : true;
  }
  void begin(LinkOptions options = LinkOptions{})
  {
    if (hasHtt) options.htt = &htt;
    linkBegin(link, ce, device.io(), options, now);
  }
  // One turn: the chip, the firmware, then the driver.
  void turn(uint32_t ms = 5)
  {
    device.run();
    firmware.drain();
    device.run();
    now += ms;
    linkRun(link, now);
  }
  int run(unsigned turns = 400)
  {
    for (unsigned i = 0; i < turns; ++i) {
      turn();
      if (link.step == kLinkDone || link.step == kLinkStopped || link.step == kLinkHandOff) break;
    }
    settle();
    return link.step;
  }
  // The chip and the firmware take what the last turn put on the rings (the driver is done, the hardware is not).
  void settle()
  {
    for (unsigned i = 0; i < 2; ++i) {
      device.run();
      firmware.drain();
    }
  }
};

// ============================================================================================ the copy engine's registers
static void testRings()
{
  Host h;
  CHECK(h.start());
  // Every pipe of kCeHostPipes has the rings its entry asks for, and nothing else.
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    const CeHostPipe &want = kCeHostPipes[i];
    const CePipe &pipe = h.ce.pipes[i];
    CHECK(pipe.pipe == want.pipe);
    CHECK(pipe.hasSrc == (want.srcEntries != 0) && pipe.hasDst == (want.dstEntries != 0));
    if (pipe.hasSrc) {
      const uint32_t unit = kUnitCe0Src + want.pipe * kCeUnitStride;
      Device::Ring ring = h.device.ring(unit, unit + kCeR2Hp, true);
      CHECK(ring.base == pipe.src.bus && ring.entries == want.srcEntries && ring.words == kCeSrcDescWords);
      CHECK(ring.enabled && ring.pointer == pipe.src.theirsBus);
      CHECK((h.device.regs[unit + kRingMisc] & kRingMiscLoopCountDisable) != 0);
      CHECK(h.device.regs[unit + kSrcRingConsumerInt0] == 0 && h.device.regs[unit + kSrcRingConsumerInt1] == 0);
    }
    if (!pipe.hasDst) continue;
    const uint32_t unit = kUnitCe0Dst + want.pipe * kCeUnitStride;
    Device::Ring dst = h.device.ring(unit, unit + kCeR2Hp, true);
    CHECK(dst.base == pipe.dst.bus && dst.entries == want.dstEntries && dst.words == kCeDstDescWords && dst.enabled);
    CHECK((h.device.regs[unit + kCeDstRingCtrl] & kCeDstRingCtrlMaxLen) == want.bufferBytes);
    Device::Ring status = h.device.ring(unit + kCeStatusRingBase, unit + kCeStatusR2Hp, false);
    CHECK(status.base == pipe.status.bus && status.entries == want.dstEntries && status.words == kCeStatusDescWords);
    CHECK(status.enabled && status.pointer == pipe.status.theirsBus);
    CHECK(status.ringId == ((kRingIdCe0DstStatus + want.pipe) & 0xffu));   // only the rings the chip produces into carry one
    // Every buffer but the two elements a ring leaves free was posted.
    CHECK(pipe.rxCount == want.dstEntries - kCeDstKeepFree);
    CHECK(h.device.regs[unit + kCeR2Hp] == pipe.rxCount * kCeDstDescWords);
  }
  // A message out and its completion.
  const int buffer = ceClaim(h.ce);
  CHECK(buffer == 0);
  std::memset(h.ce.tx[buffer].va, 0x5a, 64);
  CHECK(ceSend(h.ce, h.device.io(), kCePipeMsgOut, unsigned(buffer), 64, 0x1234));
  CHECK(h.ce.tx[buffer].busy);
  h.device.run();
  CHECK(h.device.fromHost.size() == 1 && h.device.fromHost[0].first == 3 && h.device.fromHost[0].second.size() == 64);
  unsigned sent = 0, received = 0;
  cePoll(h.ce, h.device.io(), [&](uint32_t kind, uint32_t, uint8_t *, uint32_t, uint32_t) {
    if (kind == kCeSent) ++sent;
    if (kind == kCeReceived) ++received;
  });
  CHECK(sent == 1 && received == 0 && !h.ce.tx[buffer].busy);
  // A message in: the chip fills a posted buffer and reports it in the status ring.
  std::vector<uint8_t> message(100, 0xa5);
  h.device.toHost.push_back({2, message});
  h.device.run();
  uint32_t length = 0;
  cePoll(h.ce, h.device.io(), [&](uint32_t kind, uint32_t pipe, uint8_t *va, uint32_t bytes, uint32_t) {
    if (kind != kCeReceived) return;
    ++received;
    length = bytes;
    CHECK(pipe == 2 && va[0] == 0xa5);
  });
  CHECK(received == 1 && length == 100);
  CHECK(h.ce.received == 1 && h.ce.sent == 1 && h.ce.dropped == 0);
  // The buffer is free again once it has been given back.
  CHECK(cePostRx(h.ce, h.device.io(), kCePipeMsgIn) == 1);

  // A ring never has every element filled: the last claim is refused.
  Host full;
  CHECK(full.start());
  unsigned claims = 0;
  for (;;) {
    const int slot = ceClaim(full.ce);
    if (slot < 0) break;
    if (!ceSend(full.ce, full.device.io(), kCePipeCtrlOut, unsigned(slot), 16, 0)) break;
    ++claims;
  }
  CHECK(claims == kCeSendBuffers);     // our own send buffers run out before pipe 0's sixteen elements do
  CHECK(full.ce.refused >= 1);

  // The teardown disables every ring.
  ceStop(h.ce, h.device.io());
  for (unsigned i = 0; i < kCeHostPipeCount; ++i) {
    const CeHostPipe &want = kCeHostPipes[i];
    if (want.srcEntries) CHECK(h.device.regs[kUnitCe0Src + want.pipe * kCeUnitStride + kRingMisc] == 0);
    if (want.dstEntries) CHECK(h.device.regs[kUnitCe0Dst + want.pipe * kCeUnitStride + kRingMisc] == 0);
  }

  // An arena with no room is refused, and nothing of it is used.
  Ce small;
  Arena tiny;
  std::vector<uint8_t> little(32 * 1024, 0);
  arenaInit(tiny, little.data(), kBusBase, uint32_t(little.size()));
  CHECK(!cePlan(small, tiny));
}

// ================================================================================================ the ladder, end to end
static void testLadder()
{
  Host h;
  CHECK(h.start());
  LinkOptions options;
  h.begin(options);
  h.firmware.sendReady();
  CHECK(h.run() == kLinkDone);
  CHECK(h.link.error == kLinkErrNone && linkFinished(h.link));
  // The transport's handshake.
  CHECK(h.firmware.connectSeen && h.firmware.setupSeen);
  CHECK(h.link.htc.credits == h.firmware.credits && h.link.htc.creditSize == h.firmware.creditSize);
  CHECK(h.link.endpoint == int(h.firmware.wmiEndpoint));
  CHECK(h.link.htc.ep[h.firmware.wmiEndpoint].ulPipe == 3 && h.link.htc.ep[h.firmware.wmiEndpoint].dlPipe == 2);
  CHECK(h.link.htc.creditReports >= 1 && h.link.htc.creditsGiven >= 1);
  // The chip's capability, as the firmware answered it.
  CHECK(h.link.caps.seen && h.link.caps.rfChains == 2 && h.link.caps.boardId == 0x21 && h.link.caps.memRequests == 0);
  CHECK(h.link.caps.bitmapSeen && h.link.caps.serviceBitmap[0] == 0x1);
  // The initialisation command the firmware read back: the resource configuration of this chip's own entry.
  CHECK(h.firmware.initSeen && h.firmware.initWords == kWmiResourceConfigWords);
  CHECK(h.firmware.cfg[0] == kWmiCfgNumVdevs && h.firmware.cfg[1] == kWmiCfgNumPeers && h.firmware.cfg[5] == kWmiCfgNumTids);
  CHECK(h.firmware.cfg[7] == 3 && h.firmware.cfg[8] == 3);                      // two chains: the mask is 0b11
  CHECK(h.firmware.cfg[9] == kWmiCfgRxTimeoutLoPri && h.firmware.cfg[12] == kWmiCfgRxTimeoutHiPri);
  CHECK(h.firmware.cfg[13] == kWmiCfgDecapModeNativeWifi && h.firmware.cfg[53] == kWmiCfgUsePdevId);
  CHECK(h.firmware.cfg[56] == kWmiCfgPeerMapUnmapVersion);
  CHECK(h.firmware.cfg[43] == kWmiCfgFlag1 && h.firmware.cfg[67] == kWmiCfgFlags2);
  CHECK(h.firmware.cfg[28] == kWmiCfgNumMsduDesc && h.firmware.cfg[21] == kWmiCfgTxDbgLogSize);
  // The ready event: the chip's own address, which the macOS side will publish.
  CHECK(h.link.ready.seen && std::memcmp(h.link.ready.mac, h.firmware.mac, 6) == 0);
  // The virtual device: a station, with the chip's address and one stream entry per band.
  CHECK(h.firmware.vdevSeen && h.firmware.vdevType == kWmiVdevTypeStation && h.firmware.vdevStreams == kWmiBandCount);
  CHECK(std::memcmp(h.firmware.vdevMac, h.firmware.mac, 6) == 0);
  // The scan: passive, every channel of the two bands, and no network asked for by name.
  CHECK(h.firmware.scanSeen && (h.firmware.scanFlags & kWmiScanFlagPassive));
  CHECK(h.firmware.scanFlags & kWmiScanFlagChanStatEvent);
  // P23b: the channels the firmware's regulatory event allows (the model's: the lower band, 5180-5240 and the radar channels
  // 5260-5320), not the static 22 — the radar ones included, which a passive scan may listen on.
  CHECK(h.link.chanListFromEvent && h.firmware.scanChannels == h.link.chanList.count && h.firmware.scanChannels == 21);
  CHECK(h.firmware.channelList.size() == 21 && h.firmware.channelList[0] == kScanChannels24[0]);
  CHECK(h.firmware.channelList[kScanChannelCount24] == kScanChannels5[0]);
  CHECK(std::find(h.firmware.channelList.begin(), h.firmware.channelList.end(), 5260u) != h.firmware.channelList.end());
  CHECK(h.firmware.scanSsids == 0 && h.firmware.scanBssids == 1);
  // What the scan found: three networks, the strongest signal of the repeated one, the one with no name marked.
  CHECK(h.link.scanStarted && h.link.scanCompleted && h.link.scanReason == kWmiScanReasonCompleted);
  CHECK(h.link.scan.count == 3 && h.link.scan.frames == 4 && h.link.scan.beacons == 3 && h.link.scan.probes == 1);
  CHECK(std::string(h.link.scan.entries[0].ssid) == "piano-test" && h.link.scan.entries[0].rssi == -30);
  CHECK(h.link.scan.entries[0].beacons == 2 && h.link.scan.entries[0].channel == 6 && h.link.scan.entries[0].freq == 2437);
  CHECK(h.link.scan.entries[1].hidden && h.link.scan.entries[1].ssidLength == 0 && h.link.scan.entries[1].freq == 5180);
  CHECK(std::string(h.link.scan.entries[2].ssid) == "piano-probe" && h.link.scan.entries[2].probes == 1);
  CHECK(h.link.scan.dropped == 0 && h.link.scan.ignored == 0);
  // The teardown: nothing to stop (the scan ended by itself), the virtual device deleted.
  CHECK(!h.firmware.stopSeen && h.firmware.deleteSeen);
  CHECK(h.link.unexpected == 0 && h.ce.dropped == 0 && h.ce.refused == 0);
  // Every step was announced, in the ladder's order: 601, the data interface (625), 602 to 606, the radio's set-up (620-623,
  // whose numbers are above the ladder's so that the older ones keep their meaning), 607 to 609, the statistics (626), the
  // data interface's version and the receive rings (627, 628), the second round (608, 609, 626), the teardown and done.
  static const int expected[] = {kLinkTransport, kLinkConnectHtt, kLinkConnect,    kLinkSetup,      kLinkCapability,
                                 kLinkInit,      kLinkReadyWait,  kLinkHwMode,     kLinkPdevParams, kLinkChanList,
                                 kLinkVdev,      kLinkScanStart,  kLinkScanning,   kLinkStats,      kLinkHttVersion,
                                 kLinkRxRings,   kLinkScanStart,  kLinkScanning,   kLinkStats,      kLinkTeardown,
                                 kLinkDone};
  CHECK(h.steps.size() == sizeof expected / sizeof expected[0]);
  for (unsigned i = 0; i < h.steps.size() && i < sizeof expected / sizeof expected[0]; ++i) CHECK(h.steps[i].first == expected[i]);
  // The address in a log line: masked unless the owner asked for all of it.
  char masked[32] = {}, full[32] = {};
  scanFormatBssid(h.link.scan.entries[0], false, masked, sizeof masked);
  scanFormatBssid(h.link.scan.entries[0], true, full, sizeof full);
  CHECK(std::string(masked) == "02:11:22:**:**:**");
  CHECK(std::string(full) == "02:11:22:33:44:55");
}

// ====================================================== the radio's set-up before the virtual device (P22, section 10.27)
static void testRadioSetup()
{
  {   // the whole order: the hardware mode, the six parameters, the regulatory event, the channel list, the device, the scan
    Host h;
    CHECK(h.start());
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(h.firmware.hwModeSeen && h.firmware.hwModeIndex == kWmiHwModeDbs && h.firmware.hwModePdev == kWmiPdevIdSoc);
    CHECK(h.firmware.hwModeBands == 0);
    CHECK(h.link.hwModeSent && h.link.hwModeAnswered && h.link.hwModeStatus == 0);
    CHECK(h.firmware.paramsSeen == kPdevParamCount && h.firmware.params.size() == kPdevParamCount);
    CHECK(h.firmware.params[0].first == kWmiPdevParamPmfQos && h.firmware.params[0].second == 1);
    CHECK(h.firmware.params[1].first == kWmiPdevParamDynamicBw && h.firmware.params[1].second == 1);
    CHECK(h.firmware.params[2].first == kWmiPdevParamArpAcOverride && h.firmware.params[2].second == 0);
    CHECK(h.firmware.params[3].first == kWmiPdevParamMeshMcastEnable && h.firmware.params[3].second == 1);
    CHECK(h.firmware.params[4].first == kWmiPdevParamTxChainMask && h.firmware.params[4].second == 0x3);
    CHECK(h.firmware.params[5].first == kWmiPdevParamRxChainMask && h.firmware.params[5].second == 0x3);
    // The regulatory event the firmware sent, as the driver read it.
    CHECK(h.link.reg.seen && !h.link.reg.extended && std::string(h.link.reg.alpha2) == "CN");
    CHECK(h.link.reg.rules24 == 1 && h.link.reg.rules5 == 2 && h.link.reg.ruleCount == 3 && h.link.reg.rulesDropped == 0);
    CHECK(h.link.reg.dfsRegion == 2 && h.link.reg.maxBw5 == 80);
    // The channel list: only the channels its rules allow, the radar ones marked passive.
    CHECK(h.firmware.chanListSeen && h.link.chanListSent && h.link.chanListFromEvent);
    CHECK(h.firmware.chanListPdev == kWmiPdevIdSoc && h.firmware.chanListFlags == 0);
    CHECK(h.firmware.chanListCount == h.link.chanList.count && h.firmware.chanListCount > 0);
    CHECK(h.link.chanList.count == 13 + 4 + 4);     // the lower band whole, 5180-5240 and 5260-5320
    CHECK(h.link.chanList.radar == 4 && h.link.chanList.passive == 4);
    CHECK(h.link.chanList.left5 == 17);             // every 5 GHz channel outside the rules
    bool found5180 = false, found5260Passive = false, found5500 = false;
    for (const auto &entry : h.firmware.chanEntries) {
      if (entry.first == 5180) found5180 = (entry.second & kWmiChanInfoModeMask) == kWmiModeLegacy5;
      if (entry.first == 5260) found5260Passive = (entry.second & kWmiChanInfoPassive) && (entry.second & kWmiChanInfoDfs);
      if (entry.first == 5500) found5500 = true;
    }
    CHECK(found5180 && found5260Passive && !found5500);
    // The order the commands went out in: the mode, the parameters, the list, the device, the scan.
    const std::vector<uint32_t> &order = h.firmware.commandOrder;
    CHECK(order.size() >= 10);
    CHECK(order[0] == uint32_t(kWmiCmdInit));
    CHECK(order[1] == uint32_t(kWmiCmdPdevSetHwMode));
    for (unsigned i = 0; i < kPdevParamCount; ++i) CHECK(order[2 + i] == uint32_t(kWmiCmdPdevSetParam));
    CHECK(order[2 + kPdevParamCount] == uint32_t(kWmiCmdScanChanList));
    CHECK(order[3 + kPdevParamCount] == uint32_t(kWmiCmdVdevCreate));
    CHECK(order[4 + kPdevParamCount] == uint32_t(kWmiCmdStartScan));
    CHECK(h.link.scan.count == 3 && h.link.unexpected == 0 && h.link.unknownEvents == 0);
  }
  {   // the extended regulatory event: the same rules, read through the longer header and the wider rule
    Host h;
    CHECK(h.start());
    h.firmware.regExtended = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(h.link.reg.seen && h.link.reg.extended && h.link.reg.ruleCount == 3);
    CHECK(h.link.chanListFromEvent && h.link.chanList.count == 21 && h.link.chanList.radar == 4);
  }
  {   // a firmware that sends no regulatory event: the wait runs out and the list is this driver's own
    Host h;
    CHECK(h.start());
    h.firmware.sendReg = false;
    LinkOptions options;
    options.regWaitMs = 60;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(!h.link.reg.seen && h.link.chanListSent && !h.link.chanListFromEvent);
    CHECK(h.link.chanList.count == kAssocChannelCount && h.link.chanList.radar > 0);
    CHECK(h.firmware.chanListCount == kAssocChannelCount);
  }
  {   // the address of the virtual device: the firmware's own when it has one
    Host h;
    CHECK(h.start());
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(std::memcmp(h.firmware.vdevMac, h.firmware.mac, 6) == 0);
    CHECK(std::string(h.link.vdevMacFrom).find("ready event") != std::string::npos);
  }
  {   // the firmware's own address is all zeros but one address follows the event: that one is used (the tablet's case)
    Host h;
    CHECK(h.start());
    std::memset(h.firmware.mac, 0, sizeof h.firmware.mac);
    h.firmware.extraMacs = 1;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(h.link.ready.extraMacSeen);
    CHECK(std::memcmp(h.firmware.vdevMac, h.firmware.extraMac, 6) == 0);
  }
  {   // no address anywhere: a locally administered one of piano's own, and never all zeros
    Host h;
    CHECK(h.start());
    std::memset(h.firmware.mac, 0, sizeof h.firmware.mac);
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(std::memcmp(h.firmware.vdevMac, kLocalMac, 6) == 0);
    CHECK((h.firmware.vdevMac[0] & 0x3) == 0x2);   // locally administered, not a group address
  }
  {   // every piece off: the ladder is the one of the first level 6 boot (a device straight after the ready event)
    Host h;
    CHECK(h.start());
    LinkOptions options;
    options.pre = 0;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(!h.firmware.hwModeSeen && h.firmware.paramsSeen == 0 && !h.firmware.chanListSeen);
    CHECK(h.firmware.commandOrder[1] == uint32_t(kWmiCmdVdevCreate));
  }
  {   // bit 6: no scan at all — the device is created, the level holds, then the teardown deletes it
    Host h;
    CHECK(h.start());
    LinkOptions options;
    options.pre = kPreDefault | kPreNoScan;
    options.holdMs = 60;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(h.firmware.vdevSeen && !h.firmware.scanSeen && h.firmware.deleteSeen);
    CHECK(h.link.scan.count == 0 && h.link.error == kLinkErrNone);
  }
  {   // a hardware mode the firmware refuses: logged, and the ladder goes on (its own host does not wait for the answer)
    Host h;
    CHECK(h.start());
    h.firmware.hwModeStatus = 1;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(800) == kLinkDone);
    CHECK(h.link.hwModeAnswered && h.link.hwModeStatus == 1 && h.link.error == kLinkErrNone);
  }
  {   // an event this level knows nothing about: its identifier is kept for the log
    Host h;
    CHECK(h.start());
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    for (unsigned i = 0; i < 800 && h.link.step != kLinkScanning; ++i) h.turn();
    uint8_t buffer[32] = {};
    put32(buffer, 16u | uint32_t(0x123) << kWmiTlvTagShift);
    h.firmware.event(0x04044, buffer, 4 + 16);
    h.turn();
    h.turn();
    CHECK(h.link.unknownEvents == 1 && h.link.unknownEvent[0] == 0x04044);
    CHECK(h.run(800) == kLinkDone);
  }
}

// ================================================= the receive buffers and the scan's diagnostics (P23, section 10.28)
static void testReceiveBuffers()
{
  {   // the tablet's case: a radio that keeps no frame without the host's buffers — none in the first round, all in the second
    Host h;
    CHECK(h.start());
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(h.link.error == kLinkErrNone);
    // the data interface, before the message interface, then its version
    CHECK(h.firmware.httConnectSeen && h.link.httEndpoint == int(h.firmware.httEndpoint) && !h.link.httRefused);
    CHECK(h.link.endpoint == int(h.firmware.wmiEndpoint));
    CHECK(h.link.htc.ep[h.firmware.httEndpoint].ulPipe == 4 && h.link.htc.ep[h.firmware.httEndpoint].dlPipe == 1);
    CHECK(!h.link.htc.ep[h.firmware.httEndpoint].creditFlow);
    CHECK(h.firmware.httVersionSeen && h.htt.versionSeen && h.htt.versionMajor == kHttVersionMajor);
    CHECK(h.firmware.httOption == (kHttOptionTclMetadataVersion | kHttOptionTclMetadataLength << 8 | kHttTclMetadataV2 << 16));
    // the six rings, as the firmware read them
    CHECK(h.firmware.srngSeen == kHttRings && h.htt.announced == kHttRings && h.link.srngSent == kHttRings);
    const auto *refill = h.firmware.ringOf(kHttRingHost1ToFwRxbuf, 0);
    CHECK(refill && refill->kind == kHttSwToSw && refill->entryWords == kRxBufEntryWords);
    CHECK(refill && refill->sizeWords == kRxRefillEntries * kRxBufEntryWords && !(refill->flags & kHttSrngLoopCountDisable));
    for (uint32_t radio = 1; radio <= kRxRadios; ++radio) {
      const auto *mac = h.firmware.ringOf(kHttRingRxdmaHostBuf, radio);
      CHECK(mac && mac->kind == kHttSwToHw && mac->sizeWords == kRxMacBufEntries * kRxBufEntryWords);
      CHECK(mac && (mac->flags & kHttSrngLoopCountDisable));
      const auto *status = h.firmware.ringOf(kHttRingRxdmaMonitorStatus, radio);
      CHECK(status && status->kind == kHttSwToHw && status->sizeWords == kRxMonStatusEntries * kRxBufEntryWords);
    }
    const auto *errors = h.firmware.ringOf(kHttRingRxdmaNonMonitorDest, 1);
    CHECK(errors && errors->kind == kHttHwToSw && errors->entryWords == kRxDmaDstEntryWords);
    // the two rounds: nothing without the buffers, everything with them
    CHECK(h.link.rounds[0].ran && h.link.rounds[0].completed && h.link.rounds[0].mgmtFrames == 0);
    CHECK(h.link.rounds[1].ran && h.link.rounds[1].completed && h.link.rounds[1].mgmtFrames == 4);
    CHECK(h.link.rounds[1].networks == 3 && h.link.scan.count == 3);
    CHECK(h.firmware.framesDropped == 4 && h.firmware.framesDelivered == 4 && h.firmware.scansSeen == 2);
    // the buffers the firmware took are the refill ring's; the manager they return to is the firmware's own by default
    CHECK(h.firmware.refillRbm == kRxBufRbmFw && h.firmware.refillCookieMax < kRxRefillEntries);
    // the status buffers the hardware took were given back, and so was every error entry
    CHECK(h.firmware.statusTaken > 0 && h.htt.statusRecycled == h.firmware.statusTaken);
    CHECK(h.htt.errorsSeen == 1);   // the one error entry of the second round (no ring existed in the first)
    CHECK(h.firmware.word(errors->tail) == h.firmware.word(errors->head));
    // the channel visits and the radio's statistics of each round: the radio hears in both
    CHECK(h.link.rounds[0].visits == 21 && h.link.rounds[1].visits == 21);   // the regulatory list's channels
    CHECK(h.link.rounds[0].visitStarts == 21);
    CHECK(h.link.rounds[0].visit[0].freq == kScanChannels24[0] && h.link.rounds[0].visit[0].rxFrames == 1500);
    CHECK(h.link.rounds[0].visit[0].noiseFloor == -96 && h.link.rounds[0].visit[0].busy == 4000);
    CHECK(h.link.rounds[0].stats.seen && h.link.rounds[0].stats.locMpdus == 0 && h.link.rounds[0].stats.rxCycles == 30000);
    CHECK(h.link.rounds[1].stats.seen && h.link.rounds[1].stats.locMpdus == 4 && h.link.rounds[1].stats.mpduErrs == 4);
    CHECK(h.firmware.statsRequests == 2);
    // the event counts: every channel-information event and every management frame, by identifier
    uint32_t chanInfo = 0, mgmt = 0, stats = 0;
    for (uint32_t i = 0; i < h.link.eventKinds; ++i) {
      if (h.link.eventCount[i].id == kWmiEvtChanInfo) chanInfo = h.link.eventCount[i].count;
      if (h.link.eventCount[i].id == kWmiEvtMgmtRx) mgmt = h.link.eventCount[i].count;
      if (h.link.eventCount[i].id == kWmiEvtUpdateStats) stats = h.link.eventCount[i].count;
    }
    CHECK(chanInfo == 4 * 21 && mgmt == 4 && stats == 2 && h.link.eventKindsDropped == 0);
    CHECK(h.link.unexpected == 0 && h.link.unknownEvents == 0 && h.ce.dropped == 0);
  }
  {   // bit 9: the buffers return to software ring 1, as the chip's own host has them
    Host h;
    CHECK(h.start(true, true));
    LinkOptions options;
    options.pre = kPreDefault | kPreRbmSw1;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(h.firmware.refillRbm == kRxBufRbmSw1 && h.link.rounds[1].mgmtFrames == 4);
  }
  {   // a firmware that refuses the data interface: no rings, one round, and the level still finishes
    Host h;
    CHECK(h.start());
    h.firmware.answerHtt = false;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(h.link.httRefused && h.link.httEndpoint < 0 && h.firmware.srngSeen == 0);
    CHECK(!h.link.rounds[1].ran && h.link.rounds[0].mgmtFrames == 0 && h.firmware.scansSeen == 1);
  }
  {   // statistics that never come: the wait runs out, they are not asked for again, the second round still runs
    Host h;
    CHECK(h.start());
    h.firmware.answerStats = false;
    LinkOptions options;
    options.statsWaitMs = 40;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(!h.link.rounds[0].stats.seen && h.firmware.statsRequests == 1);
    CHECK(h.link.rounds[1].mgmtFrames == 4);
  }
  {   // without bit 7: no data interface, four pipes' worth of messages, one round
    Host h;
    CHECK(h.start());
    LinkOptions options;
    options.pre = kPreDefault & ~kPreRxRings;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(!h.firmware.httConnectSeen && h.link.httEndpoint < 0 && h.firmware.scansSeen == 1);
    CHECK(h.link.rounds[0].stats.seen && h.link.rounds[0].mgmtFrames == 0);
  }
  {   // the first two tablet boots' level 6 (no pipe 4, no rings planned): the bit alone changes nothing
    Host h;
    CHECK(h.start(false));
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run(1200) == kLinkDone);
    CHECK(!h.firmware.httConnectSeen && h.firmware.scansSeen == 1 && !h.ce.pipes[4].hasSrc);
  }
  {   // the rings themselves: full before they are announced, one entry always free, the cookies naming their buffers
    Host h;
    CHECK(h.start());
    const HttRing &refill = h.htt.ring[kHttRefill];
    CHECK(*refill.head == (kRxRefillEntries - 1) * kRxBufEntryWords && *refill.tail == 0);
    CHECK(h.htt.refillPosted == kRxRefillEntries - 1);
    uint8_t message[64] = {};
    CHECK(httBuildSrngSetup(message, sizeof message, refill) == kHttSrngSetupWords * 4);
    CHECK(httBuildSrngSetup(message, 16, refill) == 0);
    uint8_t version[8] = {};
    CHECK(httBuildVersionReq(version, sizeof version) == 8 && httBuildVersionReq(version, 4) == 0);
    // a status ring whose hardware took everything is refilled whole, never past the one free entry
    HttRing &status = h.htt.ring[kHttStatus0];
    status.announced = true;
    *status.tail = *status.head;   // the hardware took every buffer
    httTurn(h.htt);
    CHECK(h.htt.statusRecycled == kRxMonStatusEntries - 1);
    CHECK(*status.head == ((*status.tail / kRxBufEntryWords + kRxMonStatusEntries - 1) % kRxMonStatusEntries) * kRxBufEntryWords);
    // a window too small for the rings: refused, and level 6 goes on without them
    HttRx small;
    Arena tiny;
    std::vector<uint8_t> little(256 * 1024, 0);
    arenaInit(tiny, little.data(), kBusBase, uint32_t(little.size()));
    CHECK(!httPlan(small, tiny, false));
  }
}

static void testOneBand()
{
  Host h;
  CHECK(h.start());
  LinkOptions options;
  options.with5GHz = false;
  h.begin(options);
  h.firmware.sendReady();
  CHECK(h.run() == kLinkDone);
  CHECK(h.firmware.scanChannels == kScanChannelCount24);
}

// ============================================================== level 7's hand-off: the device kept, the transport its
static unsigned gHooked;
static uint32_t gHookedId;
static bool handOffHook(void *, uint32_t id, const uint8_t *, uint32_t, uint64_t)
{
  ++gHooked;
  gHookedId = id;
  return id == uint32_t(kWmiEvtVdevStartResp);   // the hook takes this one; everything else goes on to the ladder
}

static void testHandOff()
{
  Host h;
  CHECK(h.start());
  LinkOptions options;
  options.handOff = true;
  const uint8_t own[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x07};
  options.ownMacSet = true;
  std::memcpy(options.ownMac, own, 6);
  h.begin(options);
  h.firmware.sendReady();
  CHECK(h.run() == kLinkHandOff);
  CHECK(linkFinished(h.link) && h.link.error == kLinkErrNone);
  // both rounds ran, nothing was deleted, and the device took the profile's address
  CHECK(h.firmware.scansSeen == 2 && !h.firmware.deleteSeen);
  CHECK(std::memcmp(h.firmware.vdevMac, own, 6) == 0 && std::string(h.link.vdevMacFrom) == "the join profile's address");
  CHECK(h.steps.back().first == kLinkHandOff);
  // the hook sees the events first; one it takes goes nowhere else, one it leaves is the ladder's
  h.link.hook = &handOffHook;
  gHooked = 0;
  const uint32_t unexpectedBefore = h.link.unexpected;
  uint8_t resp[4 + 6 * 4] = {};
  put32(resp, (6 * 4) | uint32_t(kWmiTagVdevStartRespEvent) << kWmiTlvTagShift);
  h.firmware.event(kWmiEvtVdevStartResp, resp, sizeof resp);
  for (unsigned i = 0; i < 4; ++i) h.turn();
  CHECK(gHooked == 1 && gHookedId == uint32_t(kWmiEvtVdevStartResp) && h.link.hooked == 1);
  CHECK(h.link.unexpected == unexpectedBefore);
  // level 7's own command through the ladder's endpoint, credits and all
  uint8_t msg[128] = {};
  WmiWriter w;
  const uint32_t length = assocBuildVdevSetParam(w, msg, sizeof msg, 0, kWmiVdevParamNss, 2);
  CHECK(length && linkSendWmi(h.link, msg, length) == 1);
  for (unsigned i = 0; i < 4; ++i) h.turn();
  CHECK(h.firmware.vdevParams.size() == 1 && h.firmware.vdevParams[0].first == kWmiVdevParamNss &&
        h.firmware.vdevParams[0].second == 2);
  CHECK(h.link.step == kLinkHandOff);
  // the owner's teardown after its join: the device deleted, the rings disabled
  bool idle = false;
  for (unsigned i = 0; i < 20 && !idle; ++i) {
    h.device.run();
    h.firmware.drain();
    h.device.run();
    h.now += 5;
    idle = linkStopRequest(h.link, h.now);
  }
  h.settle();
  CHECK(idle && h.firmware.deleteSeen);
  // without the hand-off the same ladder tears down as before
  Host plain;
  CHECK(plain.start());
  plain.begin(LinkOptions{});
  plain.firmware.sendReady();
  CHECK(plain.run() == kLinkDone && plain.firmware.deleteSeen);
}

static void testFaults()
{
  {   // the firmware refuses the service
    Host h;
    CHECK(h.start());
    h.firmware.connectStatus = 1;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkStopped);
    CHECK(h.link.error == kLinkErrRefused && h.link.failedStep == kLinkConnect);
  }
  {   // a firmware that wants memory this level does not hand out
    Host h;
    CHECK(h.start());
    h.firmware.memRequests = 3;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkStopped);
    CHECK(h.link.error == kLinkErrMemory && h.link.failedStep == kLinkCapability);
    CHECK(!h.firmware.initSeen);
  }
  {   // a chip that never speaks: the first step times out and nothing was sent
    Host h;
    CHECK(h.start());
    LinkOptions options;
    options.timeoutMs = 50;
    h.begin(options);
    CHECK(h.run(40) == kLinkStopped);
    CHECK(h.link.error == kLinkErrTimeout && h.link.failedStep == kLinkTransport);
    CHECK(h.ce.sent == 0);
  }
  {   // a scan that is never started by the firmware: the step times out
    Host h;
    CHECK(h.start());
    h.firmware.answerScanStarted = false;
    h.firmware.sendBeacons = false;
    h.firmware.answerScanCompleted = false;
    LinkOptions options;
    options.scanWaitMs = 60;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run() == kLinkStopped);
    CHECK(h.link.error == kLinkErrTimeout && h.link.failedStep == kLinkScanning);
    CHECK(h.firmware.scanSeen && !h.link.scanStarted);
  }
  {   // a scan that starts, reports networks and then stops answering: what it found stands and the teardown runs
    Host h;
    CHECK(h.start());
    h.firmware.answerScanCompleted = false;
    h.firmware.rxNeedsRings = false;   // a radio that keeps frames without the host's buffers: the first round finds them
    LinkOptions options;
    options.scanWaitMs = 60;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.error == kLinkErrNone && h.link.scanTimedOut && h.link.scanCompleted);
    CHECK(h.link.scanReason == kWmiScanReasonCancelled);   // the firmware's own last word on it
    CHECK(h.link.scan.count == 3 && h.firmware.stopSeen && h.firmware.deleteSeen);
  }
  {   // a management frame whose header lies about the frame's length: counted, never read past
    Host h;
    CHECK(h.start());
    h.firmware.badFrameLength = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.scan.count == 0 && h.link.unexpected >= 4);
  }
  {   // a frame that ends in the middle of its body: no entry, and the frame is counted as one this driver cannot read
    Host h;
    CHECK(h.start());
    h.firmware.shortBeacon = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.scan.ignored == 2 && h.link.scan.count == 2);
  }
  {   // more networks than the list holds: the rest are counted, nothing is overwritten
    Host h;
    CHECK(h.start());
    h.firmware.manyNetworks = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.scan.count == kScanEntriesMax && h.link.scan.dropped >= 4);
    CHECK(std::string(h.link.scan.entries[0].ssid) == "piano-test");
  }
  {   // an event in a step that does not wait for it: counted, never acted on
    Host h;
    CHECK(h.start());
    h.firmware.wrongStepEvent = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.unexpected == 2);   // one in each scan round
  }
  {   // a firmware that sends no extended capability event: the initialisation goes out when the short wait is over
    Host h;
    CHECK(h.start());
    h.firmware.sendExtended = false;
    LinkOptions options;
    options.extWaitMs = 40;
    h.begin(options);
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.extEvents == 0 && h.firmware.initSeen && h.link.error == kLinkErrNone);
  }
  {   // frames the firmware's own checks failed on: counted, and no network of theirs is believed
    Host h;
    CHECK(h.start());
    h.firmware.badStatus = true;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    CHECK(h.run() == kLinkDone);
    CHECK(h.link.scan.count == 0 && h.link.scan.badFrames == 4 && h.link.scan.ignored == 0);
  }
  {   // a message the transport cannot read is dropped and counted, and the ladder goes on
    Host h;
    CHECK(h.start());
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    for (unsigned i = 0; i < 400 && h.link.step != kLinkScanning; ++i) h.turn();
    std::vector<uint8_t> rubbish(kHtcHeaderBytes + 4, 0);
    put32(rubbish.data(), 2u | 4096u << kHtcHdrLengthShift);   // a header that does not fit its buffer
    h.device.toHost.push_back({2, rubbish});
    h.turn();
    CHECK(h.link.badMessages == 1 && h.link.error == kLinkErrNone);
    CHECK(h.run() == kLinkDone);   // and the ladder finishes all the same
  }
  {   // the owner gives up in the middle: the scan is stopped, the device deleted, the rings disabled
    Host h;
    CHECK(h.start());
    h.firmware.answerScanCompleted = false;
    h.firmware.sendBeacons = false;
    h.begin(LinkOptions{});
    h.firmware.sendReady();
    for (unsigned i = 0; i < 400 && !h.link.scanStarted; ++i) h.turn();
    CHECK(h.link.step == kLinkScanning && h.link.scanStarted);
    // The owner's bounded wait: the two commands out and taken by the chip, and only then the rings disabled.
    bool idle = false;
    for (unsigned i = 0; i < 20 && !idle; ++i) {
      idle = linkStopRequest(h.link, h.now);
      h.now += 5;
      h.device.run();
      h.firmware.drain();
    }
    CHECK(idle && h.link.stopped && h.link.deleted);
    CHECK(h.firmware.stopSeen && h.firmware.deleteSeen);
    linkDisable(h.link);
    CHECK(h.device.regs[kUnitCe0Src + 3 * kCeUnitStride + kRingMisc] == 0);
    CHECK(h.device.regs[kUnitCe0Dst + 2 * kCeUnitStride + kRingMisc] == 0);
  }
}

// ========================================================================================= the transport on its own
static void testTransport()
{
  Htc htc;
  htcBegin(htc);
  CHECK(htc.ep[0].used && htc.ep[0].ulPipe == 0 && htc.ep[0].dlPipe == 2 && !htc.ep[0].creditFlow);
  // A ready message, then its credit arithmetic.
  uint8_t ready[12] = {};
  put32(ready, uint32_t(kHtcMsgReady) | 4u << kHtcReadyCreditCountShift);
  put32(ready + 4, 1024u | 8u << kHtcReadyEndpointsShift);
  CHECK(htcParseReady(htc, ready, sizeof ready));
  CHECK(htc.credits == 4 && htc.creditSize == 1024 && htc.ready);
  CHECK(htcCreditsFor(htc, 100) == 1 && htcCreditsFor(htc, 1024) == 1 && htcCreditsFor(htc, 1025) == 2);
  // A ready message with no credits at all is a failure.
  Htc empty;
  htcBegin(empty);
  uint8_t none[8] = {};
  put32(none, uint32_t(kHtcMsgReady));
  CHECK(!htcParseReady(empty, none, sizeof none) && empty.error != nullptr);
  // A connect answer, the endpoint it gives, and its credits.
  uint8_t answer[12] = {};
  put32(answer, uint32_t(kHtcMsgConnectServiceResp) | uint32_t(kSvcWmiControl) << kHtcServiceShift);
  put32(answer + 4, 0u | 2u << kHtcRespEndpointShift | 2048u << kHtcRespMaxMessageShift);
  HtcConnect connect;
  CHECK(htcParseConnectResp(htc, answer, sizeof answer, connect));
  CHECK(connect.endpoint == 2 && connect.maxMessage == 2048 && !connect.refused);
  CHECK(htcEndpointOpen(htc, connect, 3, 2, true, htc.credits));
  CHECK(htcEndpointOf(htc, uint16_t(kSvcWmiControl)) == 2);
  CHECK(htc.ep[2].credits == 4);
  // A refused service, and an answer naming an endpoint this driver cannot use.
  uint8_t refused[12] = {};
  put32(refused, uint32_t(kHtcMsgConnectServiceResp) | uint32_t(kSvcWmiControl) << kHtcServiceShift);
  put32(refused + 4, 2u | 3u << kHtcRespEndpointShift | 2048u << kHtcRespMaxMessageShift);
  HtcConnect bad;
  CHECK(!htcParseConnectResp(htc, refused, sizeof refused, bad) && bad.refused);
  uint8_t zero[12] = {};
  put32(zero, uint32_t(kHtcMsgConnectServiceResp));
  put32(zero + 4, 0);
  HtcConnect none2;
  CHECK(!htcParseConnectResp(htc, zero, sizeof zero, none2) && !none2.refused);
  // Credits: four of them, then none until the firmware gives one back in a trailer.
  for (unsigned i = 0; i < 4; ++i) CHECK(htcTakeCredits(htc, 2, 1000));
  CHECK(!htcTakeCredits(htc, 2, 1000));
  uint8_t message[kHtcHeaderBytes + 8] = {};
  const uint32_t trailer = kHtcRecordHeaderBytes + kHtcCreditReportBytes;
  htcHeader(message, 2, trailer, kHtcFlagTrailerPresent, 0);
  message[4] = uint8_t(trailer);
  message[kHtcHeaderBytes] = kHtcRecordCredits;
  message[kHtcHeaderBytes + 1] = kHtcCreditReportBytes;
  message[kHtcHeaderBytes + kHtcRecordHeaderBytes] = 2;
  message[kHtcHeaderBytes + kHtcRecordHeaderBytes + 1] = 2;
  const HtcRx rx = htcReceive(htc, message, sizeof message);
  CHECK(rx.kind == kHtcNothing && htc.ep[2].credits == 2 && htc.creditsGiven == 2);
  CHECK(htcTakeCredits(htc, 2, 1000) && htcTakeCredits(htc, 2, 1000) && !htcTakeCredits(htc, 2, 1000));
  // A header that does not fit its buffer, and a trailer that does not fit its message.
  uint8_t lying[kHtcHeaderBytes + 4] = {};
  htcHeader(lying, 2, 4096, 0, 0);
  CHECK(htcReceive(htc, lying, sizeof lying).kind == kHtcBad);
  uint8_t badTrailer[kHtcHeaderBytes + 4] = {};
  htcHeader(badTrailer, 2, 4, kHtcFlagTrailerPresent, 0);
  badTrailer[4] = 200;
  CHECK(htcReceive(htc, badTrailer, sizeof badTrailer).kind == kHtcBad);
  CHECK(htcReceive(htc, nullptr, 0).kind == kHtcBad);
  // A payload on an endpoint nobody connected is counted, never delivered.
  uint8_t stray[kHtcHeaderBytes + 4] = {};
  htcHeader(stray, 5, 4, 0, 0);
  CHECK(htcReceive(htc, stray, sizeof stray).kind == kHtcNothing && htc.unexpected >= 1);
  // The credits a service may be given fit one byte: a firmware that reports more cannot hand all of them to one service.
  CHECK(htcAllocatable(4) == 4 && htcAllocatable(255) == 255 && htcAllocatable(4096) == 255);
}

// ============================================================================================ the codec on its own
static void testCodec()
{
  uint8_t buffer[256];
  WmiWriter w;
  wmiBegin(w, buffer, sizeof buffer, kWmiCmdStartScan);
  CHECK((get32(buffer) & kWmiCmdIdMask) == uint32_t(kWmiCmdStartScan));
  uint8_t *one = wmiTlv(w, kWmiTagChannel, 6);     // a value that is not a whole number of words is padded, and the
  CHECK(one && (w.length % 4) == 0);                // header carries the padded length, so a walk by it lands on the next
  CHECK((get32(one - 4) & kWmiTlvLenMask) == 8);
  CHECK((get32(one - 4) >> kWmiTlvTagShift) == uint32_t(kWmiTagChannel));
  uint8_t *two = wmiStruct(w, kWmiTagStopScanCmd, 3);
  CHECK(two && (get32(two - 4) & kWmiTlvLenMask) == 12);
  wmiPut(two, 2, 0xdeadbeef);
  CHECK(wmiGet(two, 2) == 0xdeadbeef);
  const uint32_t length = wmiEnd(w);
  CHECK(length == w.length);
  // The reader walks what the writer wrote, and stops at a header that lies.
  const uint8_t *at = buffer + kWmiCmdHeaderBytes;
  uint32_t left = length - kWmiCmdHeaderBytes;
  WmiTlvRef tlv;
  CHECK(wmiNext(at, left, tlv) && tlv.tag == uint32_t(kWmiTagChannel) && tlv.length == 8);
  CHECK(wmiNext(at, left, tlv) && tlv.tag == uint32_t(kWmiTagStopScanCmd) && tlv.length == 12);
  CHECK(!wmiNext(at, left, tlv));
  uint32_t size = 0;
  CHECK(wmiFind(buffer + kWmiCmdHeaderBytes, length - kWmiCmdHeaderBytes, kWmiTagStopScanCmd, &size) && size == 12);
  CHECK(!wmiFind(buffer + kWmiCmdHeaderBytes, length - kWmiCmdHeaderBytes, kWmiTagReadyEvent, &size));
  uint8_t liar[8] = {};
  put32(liar, 0xffu | uint32_t(kWmiTagChannel) << kWmiTlvTagShift);
  const uint8_t *p = liar;
  uint32_t rest = sizeof liar;
  CHECK(!wmiNext(p, rest, tlv));
  // A message that does not fit is refused whole.
  uint8_t small[16];
  WmiWriter tight;
  wmiBegin(tight, small, sizeof small, kWmiCmdInit);
  CHECK(wmiTlv(tight, kWmiTagInitCmd, 4) != nullptr);
  CHECK(wmiTlv(tight, kWmiTagResourceConfig, 64) == nullptr && tight.overflow && wmiEnd(tight) == 0);
  WmiWriter none;
  wmiBegin(none, buffer, 2, kWmiCmdInit);
  CHECK(none.overflow && wmiEnd(none) == 0);
  // The scan channel list of the two bands.
  WmiScanRequest request;
  wmiScanChannels(request, true);
  CHECK(request.channelCount == kScanChannelMax);
  wmiScanChannels(request, false);
  CHECK(request.channelCount == kScanChannelCount24);
  // The events' parsers refuse a message that is too short.
  WmiServiceReady caps;
  WmiReady ready;
  WmiScanEvent scan;
  WmiMgmtRx mgmt;
  uint8_t tooShort[12] = {};
  put32(tooShort, 4u | uint32_t(kWmiTagServiceReadyEvent) << kWmiTlvTagShift);
  CHECK(!wmiParseServiceReady(caps, tooShort, sizeof tooShort));
  put32(tooShort, 4u | uint32_t(kWmiTagReadyEvent) << kWmiTlvTagShift);
  CHECK(!wmiParseReady(ready, tooShort, sizeof tooShort));
  put32(tooShort, 4u | uint32_t(kWmiTagScanEvent) << kWmiTlvTagShift);
  CHECK(!wmiParseScanEvent(scan, tooShort, sizeof tooShort));
  put32(tooShort, 4u | uint32_t(kWmiTagMgmtRxHeader) << kWmiTlvTagShift);
  CHECK(!wmiParseMgmtRx(mgmt, tooShort, sizeof tooShort));

  // A firmware that sends the shorter management-frame header (no frequency): the header's channel is a channel number, and
  // the two are never mixed — the entry then carries the channel and no frequency.
  uint8_t frame[kDot11HeaderBytes + kDot11BeaconFixedBytes + 2 + 4] = {};
  frame[0] = uint8_t(kDot11SubtypeBeacon);
  const uint8_t bssid[6] = {0x02, 0x33, 0x44, 0x55, 0x66, 0x77};
  std::memcpy(frame + 16, bssid, 6);
  frame[kDot11HeaderBytes + kDot11BeaconFixedBytes] = kDot11ElementSsid;
  frame[kDot11HeaderBytes + kDot11BeaconFixedBytes + 1] = 4;
  std::memcpy(frame + kDot11HeaderBytes + kDot11BeaconFixedBytes + 2, "slow", 4);
  uint8_t event[4 + 12 * 4 + 4 + sizeof frame + 4] = {};
  put32(event, (12u * 4) | uint32_t(kWmiTagMgmtRxHeader) << kWmiTlvTagShift);
  put32(event + 4 + 4 * 0, 36);                        // the channel, as a channel number
  put32(event + 4 + 4 * 4, uint32_t(sizeof frame));
  put32(event + 4 + 4 * 1, uint32_t(-61 - kNoiseFloorDbm));   // the ratio: the strength is it plus the noise floor
  put32(event + 4 + 4 * 11, uint32_t(int32_t(-61)));
  uint32_t cursor = 4 + 12 * 4;
  put32(event + cursor, uint32_t(sizeof frame) | uint32_t(kWmiTagArrayByte) << kWmiTlvTagShift);
  std::memcpy(event + cursor + 4, frame, sizeof frame);
  cursor += 4 + ((uint32_t(sizeof frame) + 3u) & ~3u);
  CHECK(wmiParseMgmtRx(mgmt, event, cursor));
  CHECK(mgmt.freq == 0 && mgmt.channel == 36 && mgmt.rssi == -61 && mgmt.signalDbm == -61);
  ScanList list;
  const ScanEntry *entry = scanAdd(list, mgmt);
  CHECK(entry && list.count == 1);
  // the shorter header gives no frequency: the channel number names it (boot 10a: the frequency is always the channel's)
  CHECK(entry && std::string(entry->ssid) == "slow" && entry->channel == 36 && entry->freq == 5180 && entry->rssi == -61);
}

int main()
{
  testCodec();
  testTransport();
  testRings();
  testLadder();
  testRadioSetup();
  testReceiveBuffers();
  testOneBand();
  testHandOff();
  testFaults();
  std::printf(failures ? "wmi_host: %d check(s) failed\n" : "wmi_host: all passed\n", failures);
  return failures ? 1 : 0;
}
