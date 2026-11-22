"""Derive the second-scan admission check from the frozen portable link."""

import hashlib

LINK_SHA = 'b2f6085333811d104b5ac4e7a7f3448ee91ad69b704cedfb6206be1f3e2684d4'


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
