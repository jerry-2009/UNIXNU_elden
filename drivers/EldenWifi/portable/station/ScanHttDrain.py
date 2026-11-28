"""Derive the second-scan admission and TB322FC SRNG setup format."""

import hashlib

LINK_SHA = 'b2f6085333811d104b5ac4e7a7f3448ee91ad69b704cedfb6206be1f3e2684d4'
HTT_SHA = '2807bcef32b6f8dfea5c35eb5997e27eb6dbc8eb8c4f1c9371e38c3f9ec23ca9'


def link_header(data):
    if hashlib.sha256(data).hexdigest() != LINK_SHA:
        raise ValueError('Second-scan admission requires the pinned link header')
    text = data.decode()
    anchor = '''      nowMs >= link.ringSettle) {
    link.ringSettle = 0;'''
    replacement = '''      nowMs >= link.ringSettle) {
    // linkPump has consumed the source completion pointers. An HTT setup
    // descriptor submitted by the host is not necessarily consumed yet.
    if (link.httEndpoint <= 0 || link.httEndpoint >= int(kHtcEndpoints))
      return fail(link, kLinkErrState);
    const auto &endpoint = link.htc.ep[link.httEndpoint];
    const int pipe = ceIndexOf(endpoint.ulPipe);
    if (!endpoint.used || pipe < 0 || !link.ce->pipes[pipe].hasSrc)
      return fail(link, kLinkErrState);
    const CeRing &source = link.ce->pipes[pipe].src;
    if (source.taken != source.ours) {
      if (nowMs >= link.deadline) return fail(link, kLinkErrTransport);
      return link.step;
    }
    link.ringSettle = 0;'''
    if text.count(anchor) != 1:
        raise ValueError('Second scan transition differs')
    text = text.replace(anchor, replacement, 1)
    vdev_old = 'return wmiBuildVdevCreate(w, at, capacity, vdevId, mac, kWmiPdevIdSoc, chains);'
    vdev_new = ('const uint32_t n = wmiBuildVdevCreate(w, at, capacity, vdevId, mac, kWmiPdevIdSoc, chains);\n'
                '      if (n && !w.overflow) { (void)wmiTlv(w, kWmiTagArrayStruct, 0); return wmiEnd(w); }\n'
                '      return n;')
    if text.count(vdev_old) != 1:
        raise ValueError('VDEV create anchor differs')
    text = text.replace(vdev_old, vdev_new, 1)
    # r55: restore r38 WMI_INIT_CFG (flags2=0x00000220, hostSvc=0x00000010)
    f_old = '  bool ext2Seen = false;          // the second extended capability event: the last the firmware sends before it waits'
    f_new = f_old + '\n  bool serviceRegCcExt = false, servicePeerMetadataV1AB = false;\n  uint32_t peerMetadataCap = 0;'
    assert text.count(f_old) == 1
    text = text.replace(f_old, f_new, 1)

    i_old = '      return wmiBuildInit(w, at, capacity, chains);'
    i_new = """      const uint32_t n = wmiBuildInit(w, at, capacity, chains);
      if (n && !w.overflow) {
        uint32_t cfgBytes = 0;
        uint8_t *cfg = const_cast<uint8_t *>(wmiFind(at + kWmiCmdHeaderBytes, n - kWmiCmdHeaderBytes,
                                                    kWmiTagResourceConfig, &cfgBytes));
        if (!cfg || cfgBytes < kWmiResourceConfigWords * 4) return 0u;
        const uint32_t peerMetadata = link.servicePeerMetadataV1AB ? 2u : (link.peerMetadataCap & 3u);
        wmiPut(cfg, 67, (1u << 9) | ((peerMetadata & 3u) << 4));
        const uint32_t hostSvc = link.serviceRegCcExt ? (1u << 4) : 0u;
        wmiPut(cfg, 68, hostSvc);
        if (link.note) {
          static char msg[96];
          const char hex[] = "0123456789abcdef";
          const char prefix[] = "WMI_INIT_CFG svc281/svc365/cap/flags2/hostSvc ";
          unsigned atp = 0, pi = 0;
          while (prefix[pi] && atp + 1 < sizeof(msg)) msg[atp++] = prefix[pi++];
          const uint32_t vals[] = {(uint32_t)link.serviceRegCcExt, (uint32_t)link.servicePeerMetadataV1AB,
                                   link.peerMetadataCap, (1u << 9) | ((peerMetadata & 3u) << 4), hostSvc};
          for (unsigned vi = 0; vi < 5; ++vi) {
            for (int nib = 7; nib >= 0 && atp + 1 < sizeof(msg); --nib) msg[atp++] = hex[(vals[vi] >> (4 * nib)) & 15];
            if (vi + 1 < 5 && atp + 1 < sizeof(msg)) msg[atp++] = '/';
          }
          msg[atp] = 0;
          link.note(link.noteCtx, 806, msg);
        }
      }
      return n;"""
    assert text.count(i_old) == 1
    text = text.replace(i_old, i_new, 1)

    e2_old = '    if (id == uint32_t(kWmiEvtServiceReadyExt2)) link.ext2Seen = true;'
    e2_new = """    if (id == uint32_t(kWmiEvtServiceReadyExt2)) {
      link.ext2Seen = true;
      uint32_t extBytes = 0;
      const uint8_t *ext = wmiFind(payload, payloadLength, kWmiTagServiceReadyExt2Event, &extBytes);
      if (ext && extBytes >= 8 * 4) link.peerMetadataCap = wmiGet(ext, 7) & 3u;
    }"""
    assert text.count(e2_old) == 1
    text = text.replace(e2_old, e2_new, 1)

    sa_old = '  case kWmiEvtServiceAvailable:'
    sa_new = """  case kWmiEvtServiceAvailable: {
    uint32_t ext2Bytes = 0;
    const uint8_t *ext2 = wmiFind(payload, payloadLength, kWmiTagArrayUint32, &ext2Bytes);
    link.serviceRegCcExt = ext2 && ext2Bytes >= 4 && (wmiGet(ext2, 0) & (1u << 25));
    link.servicePeerMetadataV1AB = ext2 && ext2Bytes >= 16 && (wmiGet(ext2, 3) & (1u << 13));
    return;
  }"""
    assert text.count(sa_old) == 1
    text = text.replace(sa_old, sa_new, 1)
    return text.encode()


def oem_srng_header(data, *, oem_htt_v1=False):
    if hashlib.sha256(data).hexdigest() != HTT_SHA:
        raise ValueError('OEM SRNG setup requires the pinned HTT header')
    old = b'  const uint32_t bytes = kHttSrngSetupWords * 4;'
    new = b'''  // TB322FC htt_srng_setup sends 56 bytes. Its final word contains
  // IPA drop thresholds, which are unused on this polling path.
  const uint32_t bytes = (kHttSrngSetupWords + 1) * 4;'''
    if data.count(old) != 1:
        raise ValueError('SRNG setup encoder differs')
    out = data.replace(old, new, 1)
    if True:
        v_old = (b'  if (!at || capacity < 8) return 0;\r\n'
                 b'  put32(at, kHttMsgVersionReq);\r\n'
                 b'  put32(at + 4, kHttOptionTclMetadataVersion | kHttOptionTclMetadataLength << 8 | kHttTclMetadataV2 << 16);\r\n'
                 b'  return 8;')
        v_new = (b'  if (!at || capacity < 4) return 0;\r\n'
                 b'  put32(at, kHttMsgVersionReq);\r\n'
                 b'  return 4;')
        if out.count(v_old) != 1:
            v_old = v_old.replace(b'\r\n', b'\n')
            v_new = v_new.replace(b'\r\n', b'\n')
            if out.count(v_old) != 1:
                raise ValueError('HTT version request encoder differs')
        out = out.replace(v_old, v_new, 1)
    return out
