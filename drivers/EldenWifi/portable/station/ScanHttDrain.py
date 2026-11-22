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
    return text.replace(anchor, replacement, 1).encode()


def oem_srng_header(data):
    if hashlib.sha256(data).hexdigest() != HTT_SHA:
        raise ValueError('OEM SRNG setup requires the pinned HTT header')
    old = b'  const uint32_t bytes = kHttSrngSetupWords * 4;'
    new = b'''  // TB322FC htt_srng_setup sends 56 bytes. Its final word contains
  // IPA drop thresholds, which are unused on this polling path.
  const uint32_t bytes = (kHttSrngSetupWords + 1) * 4;'''
    if data.count(old) != 1:
        raise ValueError('SRNG setup encoder differs')
    return data.replace(old, new, 1)
