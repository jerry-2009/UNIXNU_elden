// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 8: the portable side of the network boundary (PianoWifiNet.h): the 802.1X port's messages read and built,
// the EAPOL frames wrapped and unwrapped, the keys' order (the pairwise key before the group key), the frame queues between
// the threads that hand frames in and the one that sends them, and the handshake's message numbers for the log. Nothing here
// locks, allocates or sleeps: the kext wraps each piece in its own lock (host tests: tests/net_host.cpp).
#pragma once
#include <stdint.h>
#include "PianoWifiNet.h"
#include "WifiHw.h"

namespace pianowifi {

namespace netdetail {
inline void put16(uint8_t *at, uint32_t v)
{
  at[0] = uint8_t(v);
  at[1] = uint8_t(v >> 8);
}
inline void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}
inline uint32_t get16(const uint8_t *at) { return uint32_t(at[0] | at[1] << 8); }
inline uint32_t get32(const uint8_t *at)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[i]) << (8 * i);
  return v;
}
inline void copy(uint8_t *to, const uint8_t *from, uint32_t n)
{
  for (uint32_t i = 0; i < n; ++i) to[i] = from[i];
}
inline void wipe(volatile uint8_t *at, uint32_t n)
{
  for (uint32_t i = 0; i < n; ++i) at[i] = 0;
}
}  // namespace netdetail

constexpr uint32_t kNetHdrBytes = sizeof(piano_wifi_8021x_hdr);
static_assert(sizeof(piano_wifi_8021x_hdr) == 8, "the header's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_link) == 164, "the link message's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_eapol) == 12, "the EAPOL part's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_key) == 48, "the key message's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_request) == 8, "the request's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_result) == 12, "the result's size is part of the boundary");
static_assert(sizeof(piano_wifi_8021x_profile) == 108, "the profile message's size is part of the boundary");

// ---------------------------------------------------------------------------------------------- the client's requests
enum NetRequestKind : uint32_t { kNetReqNone = 0, kNetReqEapol, kNetReqKey, kNetReqAuthorize, kNetReqLinkQuery, kNetReqLeave };

struct NetRequest {
  uint32_t kind = kNetReqNone;
  uint32_t type = 0, seq = 0, generation = 0;
  // EAPOL_TX
  const uint8_t *pdu = nullptr;
  uint32_t pduLength = 0;
  // KEY
  piano_wifi_8021x_key key = {};
  // LEAVE
  uint16_t reason = 0;
  int error = 0;   // why the message was refused (an errno), 0 when it was read
};

// One message of the client, read. The key's bytes are copied into the request (the caller wipes it when done).
inline NetRequest netParseRequest(const uint8_t *m, uint32_t length)
{
  using namespace netdetail;
  NetRequest r;
  if (!m || length < kNetHdrBytes || get16(m + 2) != length) {
    r.error = 22;   // EINVAL
    return r;
  }
  r.type = get16(m);
  r.seq = get32(m + 4);
  const uint8_t *body = m + kNetHdrBytes;
  const uint32_t bodyLength = length - kNetHdrBytes;
  switch (r.type) {
  case PIANO_WIFI_8021X_EAPOL_TX: {
    if (bodyLength < sizeof(piano_wifi_8021x_eapol)) break;
    r.generation = get32(body);
    r.pduLength = get16(body + 10);
    if (r.pduLength < 4 || r.pduLength > PIANO_WIFI_8021X_EAPOL_MAX || sizeof(piano_wifi_8021x_eapol) + r.pduLength != bodyLength)
      break;
    r.pdu = body + sizeof(piano_wifi_8021x_eapol);
    r.kind = kNetReqEapol;
    return r;
  }
  case PIANO_WIFI_8021X_KEY: {
    if (bodyLength != sizeof(piano_wifi_8021x_key)) break;
    copy(reinterpret_cast<uint8_t *>(&r.key), body, sizeof r.key);
    r.generation = r.key.generation;
    const bool ccmp = r.key.cipher == kRsnCipherCcmp, tkip = r.key.cipher == kRsnCipherTkip;
    if (r.key.group > 1 || (!ccmp && !tkip) || (tkip && !r.key.group)) break;
    if ((ccmp && r.key.key_len != 16) || (tkip && r.key.key_len != 32)) break;
    if ((!r.key.group && r.key.index != 0) || (r.key.group && (r.key.index < 1 || r.key.index > 3))) break;
    r.kind = kNetReqKey;
    return r;
  }
  case PIANO_WIFI_8021X_AUTHORIZE:
  case PIANO_WIFI_8021X_LINK_QUERY:
  case PIANO_WIFI_8021X_LEAVE:
    if (bodyLength != sizeof(piano_wifi_8021x_request)) break;
    r.generation = get32(body);
    r.reason = uint16_t(get16(body + 4));
    r.kind = r.type == PIANO_WIFI_8021X_AUTHORIZE ? kNetReqAuthorize : r.type == PIANO_WIFI_8021X_LEAVE ? kNetReqLeave
                                                                                                     : kNetReqLinkQuery;
    return r;
  default:
    break;
  }
  netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&r.key), sizeof r.key);
  r.kind = kNetReqNone;
  r.error = 22;
  return r;
}

inline void netWipeRequest(NetRequest &r)
{
  netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&r.key), sizeof r.key);
  r.pdu = nullptr;
}

// ------------------------------------------------------------------------------------------- the kext's messages
inline uint32_t netHeader(uint8_t *m, uint32_t type, uint32_t length, uint32_t seq)
{
  netdetail::put16(m, type);
  netdetail::put16(m + 2, length);
  netdetail::put32(m + 4, seq);
  return kNetHdrBytes;
}

inline uint32_t netBuildLink(uint8_t *m, uint32_t capacity, uint32_t seq, const piano_wifi_8021x_link &link)
{
  const uint32_t length = kNetHdrBytes + sizeof link;
  if (!m || capacity < length) return 0;
  netHeader(m, PIANO_WIFI_8021X_LINK, length, seq);
  netdetail::copy(m + kNetHdrBytes, reinterpret_cast<const uint8_t *>(&link), sizeof link);
  return length;
}

inline uint32_t netBuildProfile(uint8_t *m, uint32_t capacity, uint32_t seq, const piano_wifi_8021x_profile &profile)
{
  const uint32_t length = kNetHdrBytes + sizeof profile;
  if (!m || capacity < length) return 0;
  netHeader(m, PIANO_WIFI_8021X_PROFILE, length, seq);
  netdetail::copy(m + kNetHdrBytes, reinterpret_cast<const uint8_t *>(&profile), sizeof profile);
  return length;
}

inline uint32_t netBuildEapolRx(uint8_t *m, uint32_t capacity, uint32_t seq, uint32_t generation, const uint8_t *peer,
                                const uint8_t *pdu, uint32_t pduLength)
{
  using namespace netdetail;
  const uint32_t length = kNetHdrBytes + sizeof(piano_wifi_8021x_eapol) + pduLength;
  if (!m || !pdu || pduLength > PIANO_WIFI_8021X_EAPOL_MAX || capacity < length) return 0;
  netHeader(m, PIANO_WIFI_8021X_EAPOL_RX, length, seq);
  uint8_t *body = m + kNetHdrBytes;
  put32(body, generation);
  for (unsigned i = 0; i < 6; ++i) body[4 + i] = peer ? peer[i] : 0;
  put16(body + 10, pduLength);
  copy(body + sizeof(piano_wifi_8021x_eapol), pdu, pduLength);
  return length;
}

inline uint32_t netBuildResult(uint8_t *m, uint32_t capacity, uint32_t seq, uint32_t request, int status, uint32_t detail,
                               uint32_t generation)
{
  using namespace netdetail;
  const uint32_t length = kNetHdrBytes + sizeof(piano_wifi_8021x_result);
  if (!m || capacity < length) return 0;
  netHeader(m, PIANO_WIFI_8021X_RESULT, length, seq);
  uint8_t *body = m + kNetHdrBytes;
  put16(body, request);
  put16(body + 2, uint32_t(uint16_t(int16_t(status))));
  put32(body + 4, detail);
  put32(body + 8, generation);
  return length;
}

// ------------------------------------------------------------------------------------------------ EAPOL frames
// Our RSN element as the association request carries it (WifiDot11.h builds the same bytes): 22 bytes.
inline uint32_t netRsnElement(uint8_t *out, uint32_t capacity, uint8_t group, uint8_t pairwise, uint8_t akm)
{
  if (!out || capacity < 22) return 0;
  const uint8_t e[22] = {kDot11ElementRsn, 20, 1, 0, 0x00, 0x0f, 0xac, group, 1, 0, 0x00, 0x0f, 0xac, pairwise, 1, 0, 0x00,
                         0x0f, 0xac, akm, 0, 0};
  netdetail::copy(out, e, 22);
  return 22;
}

// An EAPOL PDU into an Ethernet frame: to the access point, from the station, type 0x888e.
inline uint32_t netEapolFrame(uint8_t *f, uint32_t capacity, const uint8_t *own, const uint8_t *bssid, const uint8_t *pdu,
                              uint32_t pduLength)
{
  if (!f || !own || !bssid || !pdu || capacity < 14 + pduLength) return 0;
  netdetail::copy(f, bssid, 6);
  netdetail::copy(f + 6, own, 6);
  f[12] = uint8_t(kEtherTypeEapol >> 8);
  f[13] = uint8_t(kEtherTypeEapol);
  netdetail::copy(f + 14, pdu, pduLength);
  return 14 + pduLength;
}

// Which message of the handshakes an EAPOL PDU is, for the log (protocol fields only, nothing of the keys): 1-4 the four-way
// handshake's, 5 the group key handshake's first, 6 its second, 0 an EAPOL frame that is not a key frame or not one of those.
struct EapolKind {
  uint32_t message = 0;
  uint32_t type = 0, descriptor = 0, keyInfo = 0, keyDataLength = 0;
};
constexpr uint32_t kEapolTypeKey = 3;
constexpr uint32_t kEapolKeyInfoPairwise = 1u << 3, kEapolKeyInfoInstall = 1u << 6, kEapolKeyInfoAck = 1u << 7,
                   kEapolKeyInfoMic = 1u << 8, kEapolKeyInfoSecure = 1u << 9, kEapolKeyInfoEncrypted = 1u << 12;
constexpr uint32_t kEapolKeyFixedBytes = 4 + 95;   // the 802.1X header and the key frame's fields up to its data length

inline EapolKind netEapolKind(const uint8_t *pdu, uint32_t length)
{
  EapolKind k;
  if (!pdu || length < 4) return k;
  k.type = pdu[1];
  if (k.type != kEapolTypeKey || length < kEapolKeyFixedBytes) return k;
  k.descriptor = pdu[4];
  k.keyInfo = uint32_t(pdu[5]) << 8 | pdu[6];
  k.keyDataLength = uint32_t(pdu[4 + 93]) << 8 | pdu[4 + 94];
  const uint32_t i = k.keyInfo;
  const bool pairwise = i & kEapolKeyInfoPairwise, ack = i & kEapolKeyInfoAck, mic = i & kEapolKeyInfoMic,
             secure = i & kEapolKeyInfoSecure, install = i & kEapolKeyInfoInstall;
  if (pairwise) {
    if (ack && !mic) k.message = 1;
    else if (ack && mic && install) k.message = 3;
    else if (!ack && mic && !secure) k.message = 2;
    else if (!ack && mic && secure) k.message = 4;
  } else {
    if (ack && mic) k.message = 5;
    else if (!ack && mic) k.message = 6;
  }
  return k;
}

inline const char *netEapolMessageName(uint32_t message)
{
  switch (message) {
  case 1: return "message 1 of the four-way handshake";
  case 2: return "message 2 of the four-way handshake";
  case 3: return "message 3 of the four-way handshake";
  case 4: return "message 4 of the four-way handshake";
  case 5: return "message 1 of the group key handshake";
  case 6: return "message 2 of the group key handshake";
  default: return "an EAPOL frame that is not one of the handshakes' key messages";
  }
}

// ---------------------------------------------------------------------------------------------- the frame queue
// Frames handed in by other threads (en0's output, the 802.1X port's EAPOL_TX) for the ladder's thread to send; a fixed ring
// of copies. EAPOL frames may go out before the port is open; the others only after. (Boot 10s: 128 slots, 32 up to 10r; boot
// 10r's uploads filled 32 at once: 3627 frames refused.)
constexpr uint32_t kNetQueueSlots = 128;
struct NetFrame {
  uint16_t length = 0;
  bool eapol = false;
  uint8_t bytes[PIANO_WIFI_NET_FRAME_MAX];
};
struct NetQueue {
  NetFrame slot[kNetQueueSlots];
  uint32_t head = 0, tail = 0;   // head: the next slot written; tail: the next one sent
  uint32_t queued = 0, full = 0, sent = 0, dropped = 0;
};

inline uint32_t netQueueCount(const NetQueue &q) { return (q.head + kNetQueueSlots - q.tail) % kNetQueueSlots; }

inline bool netQueuePut(NetQueue &q, const uint8_t *frame, uint32_t length, bool eapol)
{
  if (!frame || length < 14 || length > PIANO_WIFI_NET_FRAME_MAX) return false;
  if ((q.head + 1) % kNetQueueSlots == q.tail) {
    ++q.full;
    return false;
  }
  NetFrame &f = q.slot[q.head];
  netdetail::copy(f.bytes, frame, length);
  f.length = uint16_t(length);
  f.eapol = eapol;
  q.head = (q.head + 1) % kNetQueueSlots;
  ++q.queued;
  return true;
}

inline const NetFrame *netQueuePeek(const NetQueue &q) { return q.head == q.tail ? nullptr : &q.slot[q.tail]; }

inline void netQueuePop(NetQueue &q, bool sent)
{
  if (q.head == q.tail) return;
  q.slot[q.tail].length = 0;
  q.tail = (q.tail + 1) % kNetQueueSlots;
  if (sent) ++q.sent;
  else ++q.dropped;
}

inline void netQueueClear(NetQueue &q)
{
  while (q.head != q.tail) netQueuePop(q, false);
}

// ----------------------------------------------------------------------------------------------------- the keys
// The firmware of this chip family installs a group key only after the pairwise one: a group key that comes first waits here
// until the pairwise key's completion. One key is in flight at a time (its completion event names it).
struct NetKeys {
  piano_wifi_8021x_key pairwise = {}, group = {};
  uint32_t pairwiseSeq = 0, groupSeq = 0;
  bool pairwiseWaiting = false, groupWaiting = false;   // given by the client, not sent yet
  bool inFlight = false, inFlightGroup = false;
  uint32_t inFlightSeq = 0;
  uint64_t inFlightAt = 0;
  bool pairwiseDone = false;
  uint32_t installed = 0, refused = 0;
};

inline void netKeysReset(NetKeys &k)
{
  netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&k.pairwise), sizeof k.pairwise);
  netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&k.group), sizeof k.group);
  const uint32_t installed = k.installed, refused = k.refused;
  renew(k);
  k.installed = installed;
  k.refused = refused;
}

// A key of the client's. False (EBUSY) when one of the same kind is already waiting.
inline bool netKeysOffer(NetKeys &k, const piano_wifi_8021x_key &key, uint32_t seq)
{
  if (key.group) {
    if (k.groupWaiting) return false;
    netdetail::copy(reinterpret_cast<uint8_t *>(&k.group), reinterpret_cast<const uint8_t *>(&key), sizeof key);
    k.groupSeq = seq;
    k.groupWaiting = true;
    return true;
  }
  if (k.pairwiseWaiting) return false;
  netdetail::copy(reinterpret_cast<uint8_t *>(&k.pairwise), reinterpret_cast<const uint8_t *>(&key), sizeof key);
  k.pairwiseSeq = seq;
  k.pairwiseWaiting = true;
  return true;
}

// The key to send now, if any: the pairwise one first, a group one only after the pairwise key's completion (or when the
// pairwise key of this association was installed before). Null when nothing may go out.
inline const piano_wifi_8021x_key *netKeysNext(const NetKeys &k, uint32_t *seq)
{
  if (k.inFlight) return nullptr;
  if (k.pairwiseWaiting) {
    if (seq) *seq = k.pairwiseSeq;
    return &k.pairwise;
  }
  if (k.groupWaiting && k.pairwiseDone) {
    if (seq) *seq = k.groupSeq;
    return &k.group;
  }
  return nullptr;
}

// The key netKeysNext gave went out: its copy is wiped, its completion awaited.
inline void netKeysSent(NetKeys &k, bool group, uint64_t nowMs)
{
  k.inFlight = true;
  k.inFlightGroup = group;
  k.inFlightAt = nowMs;
  if (group) {
    k.inFlightSeq = k.groupSeq;
    k.groupWaiting = false;
    netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&k.group), sizeof k.group);
  } else {
    k.inFlightSeq = k.pairwiseSeq;
    k.pairwiseWaiting = false;
    netdetail::wipe(reinterpret_cast<volatile uint8_t *>(&k.pairwise), sizeof k.pairwise);
  }
}

// Its completion (status 0: installed). Returns the client's seq of the key it answers.
inline uint32_t netKeysDone(NetKeys &k, bool ok)
{
  if (!k.inFlight) return 0;
  k.inFlight = false;
  if (ok) {
    ++k.installed;
    if (!k.inFlightGroup) k.pairwiseDone = true;
  } else {
    ++k.refused;
  }
  return k.inFlightSeq;
}

}  // namespace pianowifi
