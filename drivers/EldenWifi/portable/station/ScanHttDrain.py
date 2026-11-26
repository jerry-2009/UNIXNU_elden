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
    init_old = 'return wmiBuildInit(w, at, capacity, chains);'
    init_new = ('const uint32_t n = wmiBuildInit(w, at, capacity, chains);\n'
                '      if (n >= 96 && wmiGet(at + 40, 13) == 1u) wmiPut(at + 40, 13, 2u);\n'
                '      return n;')
    if text.count(init_old) != 1:
        raise ValueError('WMI init anchor differs')
    text = text.replace(init_old, init_new, 1)
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
    if oem_htt_v1:
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
