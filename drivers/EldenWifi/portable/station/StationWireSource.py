"""Derive the fixed donor's station wire format for the loaded Y700 OEM.

The original donor blobs remain untouched. Sizes and mandatory tails are
confirmed by qca_cld3_peach_v2.ko SHA33869cd6 and vendor d50b305f. No board,
ring, bank, clock, timeout, key rule or credential is changed.
"""
import hashlib

ASSOC_SHA = '6ed5ee4f27ea0550b82ab536f9eec52dc76542cba9b06fae5b67ad5f8a59e788'
STATION_SHA = '7793538fc078156574e8b5d4c547186eca15b357840b145ff2547a121a86213a'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def association(data):
    if digest(data) != ASSOC_SHA:
        raise ValueError('Station wire requires the exact fixed donor codec')
    original = text = data.decode()
    changes = []
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Station wire anchor differs: ' + old[:90])
        text = text.replace(old, new, 1)
        changes.append((old, new))
    replace('wmiStruct(w, kWmiTagVdevStartCmd, kWmiVdevStartWords)',
            'wmiStruct(w, kWmiTagVdevStartCmd, 32)')
    replace('  (void)wmiTlv(w, kWmiTagArrayStruct, 0);   // no notice-of-absence descriptors\n  return wmiEnd(w);',
            '''  (void)wmiTlv(w, kWmiTagArrayStruct, 0);   // no notice-of-absence descriptors
  // Loaded OEM vdev_start_add_mlo_params emits a 12-byte structure even
  // for this non-MLO request; enabled/partner fields remain zero.
  uint8_t *mlo = wmiTlv(w, kWmiTagArrayStruct, 12);
  if (mlo) wmiPut(mlo, 0, (0x3d6u << 16) | 8u);
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);   // no partner links
  return wmiEnd(w);''')
    replace('wmiStruct(w, kWmiTagVdevUpCmd, kWmiVdevUpWords)',
            'wmiStruct(w, kWmiTagVdevUpCmd, 9)')
    replace('wmiStruct(w, kWmiTagPeerAssocCmd, kWmiPeerAssocWords)',
            'wmiStruct(w, kWmiTagPeerAssocCmd, 62)')
    replace('  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no multi-link parameters',
            '''  // OEM peer_assoc_add_mlo_params is unconditional. The disabled
  // non-MLO structure is 68 bytes including its header, with a 64-byte
  // body. No MLD address/link ID/key material is invented.
  uint8_t *mlo = wmiTlv(w, kWmiTagArrayStruct, 68);
  if (mlo) wmiPut(mlo, 0, (0x3d0u << 16) | 64u);''')
    replace('  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no multi-link partners\n  return wmiEnd(w);',
            '''  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no multi-link partners
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no TID-to-link map
  return wmiEnd(w);''')
    restored = text
    for old, new in reversed(changes):
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError('Station wire touched unrelated donor behavior')
    return text.encode()

def station(data):
    if digest(data) != STATION_SHA:
        raise ValueError('Station wire requires the qualified TX diagnostic parent')
    text = data.decode()
    old = 'static void sta_notice(void *,int step,const char *what){notice(step,what);}'
    new = old + '''
static void diag_line(const char *,const uint32_t *,unsigned);
static void station_report(void *,uint32_t what,uint32_t a,uint32_t b){
    if(what==kStaRepPeerAssocConf||what==kStaRepStartResp){
        const uint32_t values[]={what,a,b};
        diag_line("STATION_REPLY kind/status-or-confirmed/ms",values,3);
    }
}'''
    anchors = [
        (old, new),
        ('sta.note=sta_notice;sta.ctx=owner_io.owner;staBegin(sta,o,environment,now);',
         'sta.note=sta_notice;sta.report=station_report;sta.ctx=owner_io.owner;staBegin(sta,o,environment,now);'),
        ('        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);',
        '''        if(f->eapol){
            const auto kind=netEapolKind(f->bytes+14,f->length-14);
            const uint32_t values[]={kind.message,uint32_t(f->length-14)};
            diag_line("EAPOL_TX message/bytes",values,2);
        }
        const uint32_t normal_tid=dp.tid;
        if(f->eapol)dp.tid=7;
        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);
        dp.tid=normal_tid;'''),
    ]
    original = text
    for before, after in anchors:
        if text.count(before) != 1:
            raise ValueError('Station wire observer anchor differs')
        text = text.replace(before, after, 1)
    restored = text
    for before, after in reversed(anchors):
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError('Station wire changed protocol timing/rules')
    return text.encode()
