// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 6, the host transport (HTC): the control protocol the firmware speaks on top of the copy engine, as a portable
// piece the owner steps (host tests: tests/wmi_host.cpp against a firmware model). New code for this repository; the header, the
// four messages, the trailer's credit records and the connection flags are wire facts of WifiHw.h, read from the Ubuntu kernel of
// docs/drivers/wifi.md section 3 for those facts only — no code, comment or table of it is here.
//
// What it is: every message on any pipe carries an 8-byte header naming an endpoint, and endpoint 0 is the transport's own.
// The exchange, once the copy engine's rings run:
//   1. the firmware speaks first: a "ready" message on endpoint 0 with the credit count and the credit size (how large one
//      credit's worth of message is). Nothing can be sent before it;
//   2. the host connects each service it wants: a "connect service" on endpoint 0, answered with a status, the endpoint number
//      the service got and the largest message it takes. The pipes a service uses are not negotiated — they are the service
//      table level 5 already sent the firmware (WifiHw.h kCeServices);
//   3. the host says "set-up complete", and the firmware's own messages may flow;
//   4. from then on a message to a service goes out on its pipe with its endpoint in the header, and the firmware's answers come
//      back on the service's inbound pipe. A message of a service with credit flow control (the firmware's message interface is
//      the only one here) costs credits, which the firmware gives back in the trailer of messages it sends.
// Nothing here allocates, maps or sleeps: the owner owns the buffers, and every wait is the owner's bounded poll.
#pragma once
#include <stdint.h>
#include "WifiHw.h"

namespace pianowifi {

struct HtcEndpoint {
  uint16_t service = 0;
  uint8_t id = 0, ulPipe = 0, dlPipe = 0;
  bool used = false, creditFlow = false;
  int32_t credits = 0;
  uint32_t maxMessage = 0;
  uint8_t sequence = 0;
  uint32_t sent = 0, received = 0;
};

// What one received message turned out to be.
enum HtcKind : uint32_t { kHtcNothing = 0, kHtcControl, kHtcPayload, kHtcBad };

struct HtcRx {
  uint32_t kind = kHtcNothing;
  uint8_t endpoint = 0;
  uint16_t message = 0;             // a control message's identifier
  const uint8_t *payload = nullptr; // the message without its header and without its trailer
  uint32_t length = 0;
  const char *error = nullptr;
};

struct Htc {
  HtcEndpoint ep[kHtcEndpoints];
  uint32_t credits = 0, creditSize = 0, endpoints = 0, version = 0, bundle = 0;
  bool ready = false, setupSent = false;
  // counters and the last thing seen, for the log
  uint32_t rx = 0, tx = 0, creditReports = 0, creditsGiven = 0, trailers = 0, unexpected = 0, badLength = 0;
  uint16_t lastControl = 0;
  const char *error = nullptr;
};

namespace htcdetail {

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

}  // namespace htcdetail

// Endpoint 0 is the transport's own: the control service, the pipes its entry of the service table names, and no credit flow
// control (its messages are small and the firmware answers them one at a time).
inline void htcBegin(Htc &htc)
{
  renew(htc);
  HtcEndpoint &zero = htc.ep[0];
  zero.service = uint16_t(kSvcCtrl);
  zero.id = 0;
  zero.ulPipe = 0;
  zero.dlPipe = 2;
  zero.used = true;
  zero.creditFlow = false;
  zero.maxMessage = kHtcMaxControlMessage;
}

// The 8-byte header in front of a message of `payload` bytes.
inline void htcHeader(uint8_t *at, uint8_t endpoint, uint32_t payload, uint32_t flags, uint8_t sequence)
{
  using namespace htcdetail;
  put32(at, uint32_t(endpoint) | (flags & 0xffu) << kHtcHdrFlagsShift | (payload & 0xffffu) << kHtcHdrLengthShift);
  put32(at + 4, uint32_t(sequence) << kHtcCtrlSequenceShift);
}

// How many credits a message of `bytes` (header included) costs on an endpoint with credit flow control.
inline uint32_t htcCreditsFor(const Htc &htc, uint32_t bytes)
{
  if (!htc.creditSize) return 0;
  return (bytes + htc.creditSize - 1) / htc.creditSize;
}

// The firmware's "ready": the credits, the credit size, how many endpoints it has, and (in the extended form) its version.
inline bool htcParseReady(Htc &htc, const uint8_t *payload, uint32_t length)
{
  using namespace htcdetail;
  if (!payload || length < 8) {
    htc.error = "the ready message is too short";
    return false;
  }
  const uint32_t word0 = get32(payload), word1 = get32(payload + 4);
  if ((word0 & kHtcMsgIdMask) != kHtcMsgReady) {
    htc.error = "the first message is not the transport's ready";
    return false;
  }
  htc.credits = word0 >> kHtcReadyCreditCountShift;
  htc.creditSize = word1 & kHtcReadyCreditSizeMask;
  htc.endpoints = (word1 >> kHtcReadyEndpointsShift) & 0xffu;
  if (length >= 12) {
    const uint32_t word2 = get32(payload + 8);
    htc.version = word2 & 0xffu;
    htc.bundle = (word2 >> 8) & 0xffu;
  }
  if (!htc.credits || !htc.creditSize) {
    htc.error = "the ready message carries no credits";
    return false;
  }
  htc.ready = true;
  return true;
}

// How many credits a service may be given: the field in the connection flags is one byte, so a firmware that reports more
// credits than that cannot hand all of them to one service, and the host must not believe it has more than it asked for.
inline uint32_t htcAllocatable(uint32_t credits) { return credits > 0xffu ? 0xffu : credits; }

// A "connect service" request: the service, how many of the firmware's receive buffers it may have, and whether its messages
// are under credit flow control (the firmware's message interface is; everything else asks for it to be switched off).
inline uint32_t htcBuildConnect(uint8_t *payload, uint32_t capacity, uint16_t service, uint32_t recvAlloc, bool creditFlow)
{
  using namespace htcdetail;
  if (!payload || capacity < 8) return 0;
  put32(payload, uint32_t(kHtcMsgConnectService) | uint32_t(service) << kHtcServiceShift);
  uint32_t flags = (recvAlloc & 0xffu) << kHtcConnRecvAllocShift;
  if (!creditFlow) flags |= kHtcConnFlagDisableCreditFlow;
  put32(payload + 4, flags & kHtcConnFlagsMask);
  return 8;
}

struct HtcConnect {
  uint16_t service = 0;
  uint8_t status = 0, endpoint = 0;
  uint32_t maxMessage = 0;
  bool refused = false;        // the firmware answered, and said no (its status, not a fault of the message)
};

inline bool htcParseConnectResp(Htc &htc, const uint8_t *payload, uint32_t length, HtcConnect &out)
{
  using namespace htcdetail;
  if (!payload || length < 12) {
    htc.error = "the connect answer is too short";
    return false;
  }
  const uint32_t word0 = get32(payload), word1 = get32(payload + 4);
  if ((word0 & kHtcMsgIdMask) != kHtcMsgConnectServiceResp) {
    htc.error = "that is not a connect answer";
    return false;
  }
  out.service = uint16_t(word0 >> kHtcServiceShift);
  out.status = uint8_t(word1 & kHtcRespStatusMask);
  out.endpoint = uint8_t((word1 >> kHtcRespEndpointShift) & 0xffu);
  out.maxMessage = word1 >> kHtcRespMaxMessageShift;
  if (out.status != kHtcConnStatusSuccess) {
    out.refused = true;
    htc.error = "the firmware refused the service";
    return false;
  }
  if (!out.endpoint || out.endpoint >= kHtcEndpoints || !out.maxMessage || out.maxMessage > kHtcMaxMessage) {
    htc.error = "the firmware answered with an endpoint this driver cannot use";
    return false;
  }
  return true;
}

// The endpoint the answer gave, with the pipes the service table names and the credits the host asked for.
inline bool htcEndpointOpen(Htc &htc, const HtcConnect &answer, uint8_t ulPipe, uint8_t dlPipe, bool creditFlow,
                            uint32_t credits)
{
  if (answer.endpoint >= kHtcEndpoints || htc.ep[answer.endpoint].used) {
    htc.error = "the firmware gave an endpoint that is already in use";
    return false;
  }
  HtcEndpoint &ep = htc.ep[answer.endpoint];
  ep.service = answer.service;
  ep.id = answer.endpoint;
  ep.ulPipe = ulPipe;
  ep.dlPipe = dlPipe;
  ep.used = true;
  ep.creditFlow = creditFlow;
  ep.credits = creditFlow ? int32_t(credits) : 0;
  ep.maxMessage = answer.maxMessage;
  return true;
}

// "Set-up complete", the last control message of the handshake (the extended form, which is the one this chip family answers to).
inline uint32_t htcBuildSetupComplete(uint8_t *payload, uint32_t capacity)
{
  using namespace htcdetail;
  if (!payload || capacity < 12) return 0;
  put32(payload, uint32_t(kHtcMsgSetupCompleteEx));
  put32(payload + 4, 0);    // no set-up flags: no message bundling
  put32(payload + 8, 0);    // and so no bundle limit either
  return 12;
}

// The trailer's records: the only one this driver acts on is a credit report, which gives an endpoint its credits back.
inline void htcTrailer(Htc &htc, const uint8_t *at, uint32_t length)
{
  ++htc.trailers;
  while (length >= kHtcRecordHeaderBytes) {
    const uint32_t id = at[0], bytes = at[1];
    if (bytes + kHtcRecordHeaderBytes > length) {
      ++htc.unexpected;
      return;
    }
    if (id == kHtcRecordCredits) {
      for (uint32_t i = 0; i + kHtcCreditReportBytes <= bytes; i += kHtcCreditReportBytes) {
        const uint8_t endpoint = at[kHtcRecordHeaderBytes + i], credits = at[kHtcRecordHeaderBytes + i + 1];
        ++htc.creditReports;
        if (endpoint >= kHtcEndpoints || !htc.ep[endpoint].used) {
          ++htc.unexpected;
          continue;
        }
        htc.ep[endpoint].credits += credits;
        htc.creditsGiven += credits;
      }
    } else {
      ++htc.unexpected;
    }
    at += kHtcRecordHeaderBytes + bytes;
    length -= kHtcRecordHeaderBytes + bytes;
  }
}

// One message out of a receive buffer: its header checked against the buffer, its trailer taken off (and its credit reports
// acted on), and what is left handed back as a control message or as an endpoint's payload.
inline HtcRx htcReceive(Htc &htc, const uint8_t *data, uint32_t length)
{
  using namespace htcdetail;
  HtcRx out;
  if (!data || length < kHtcHeaderBytes) {
    ++htc.badLength;
    out.kind = kHtcBad;
    out.error = "a message shorter than the transport's header";
    return out;
  }
  const uint32_t word0 = get32(data), word1 = get32(data + 4);
  const uint8_t endpoint = uint8_t(word0 & kHtcHdrEndpointMask);
  const uint32_t flags = (word0 >> kHtcHdrFlagsShift) & 0xffu;
  uint32_t payload = (word0 >> kHtcHdrLengthShift) & 0xffffu;
  if (endpoint >= kHtcEndpoints || payload + kHtcHeaderBytes > length || payload + kHtcHeaderBytes > kHtcMaxMessage) {
    ++htc.badLength;
    out.kind = kHtcBad;
    out.error = "a message whose header does not fit its buffer";
    return out;
  }
  ++htc.rx;
  if (flags & kHtcFlagTrailerPresent) {
    const uint32_t trailer = (word1 >> kHtcCtrlTrailerShift) & 0xffu;
    if (trailer < kHtcRecordHeaderBytes || trailer > payload) {
      ++htc.badLength;
      out.kind = kHtcBad;
      out.error = "a trailer that does not fit its message";
      return out;
    }
    htcTrailer(htc, data + kHtcHeaderBytes + payload - trailer, trailer);
    payload -= trailer;
  }
  out.endpoint = endpoint;
  out.payload = data + kHtcHeaderBytes;
  out.length = payload;
  if (!payload) {   // a message that was nothing but a credit report
    out.kind = kHtcNothing;
    return out;
  }
  if (endpoint == 0) {
    if (payload < 4) {
      ++htc.badLength;
      out.kind = kHtcBad;
      out.error = "a control message shorter than its identifier";
      return out;
    }
    out.kind = kHtcControl;
    out.message = uint16_t(get32(out.payload) & kHtcMsgIdMask);
    htc.lastControl = out.message;
    return out;
  }
  if (!htc.ep[endpoint].used) {
    ++htc.unexpected;
    out.kind = kHtcNothing;
    return out;
  }
  ++htc.ep[endpoint].received;
  out.kind = kHtcPayload;
  return out;
}

// Before a message is sent on an endpoint with credit flow control: takes its credits, or says there are not enough yet.
inline bool htcTakeCredits(Htc &htc, uint8_t endpoint, uint32_t bytes)
{
  if (endpoint >= kHtcEndpoints || !htc.ep[endpoint].used) return false;
  HtcEndpoint &ep = htc.ep[endpoint];
  if (!ep.creditFlow) return true;
  const uint32_t need = htcCreditsFor(htc, bytes);
  if (ep.credits < int32_t(need)) return false;
  ep.credits -= int32_t(need);
  return true;
}

// The header of the next message on an endpoint (and its sequence number, which the firmware only logs).
inline uint32_t htcPrepare(Htc &htc, uint8_t endpoint, uint8_t *buffer, uint32_t payload)
{
  if (endpoint >= kHtcEndpoints || !htc.ep[endpoint].used || !buffer) return 0;
  HtcEndpoint &ep = htc.ep[endpoint];
  const uint32_t flags = ep.creditFlow ? kHtcFlagNeedCreditUpdate : 0u;
  htcHeader(buffer, endpoint, payload, flags, ep.sequence++);
  ++ep.sent;
  ++htc.tx;
  return payload + kHtcHeaderBytes;
}

inline int htcEndpointOf(const Htc &htc, uint16_t service)
{
  for (unsigned i = 0; i < kHtcEndpoints; ++i)
    if (htc.ep[i].used && htc.ep[i].service == service) return int(i);
  return -1;
}

}  // namespace pianowifi
