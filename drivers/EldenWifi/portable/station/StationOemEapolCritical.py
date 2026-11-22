"""Derive the fixed OEM EAPOL critical-queue fields over the ready object."""

import hashlib

from ProfileReadySource import derive


READY_SOURCE_SHA = '66585bb02c6a5428a23efbc1ab7de8b29482ebb202d99f500ad8ca741f81c592'
DP_SOURCE_SHA = 'e34fd826570c827b3c20790a895296a963066450790196df55b8d2d4a3afa5ef'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError('OEM EAPOL critical anchor differs: ' + label)
    return text.replace(old, new, 1)


def station(data):
    if sha(data) != READY_SOURCE_SHA:
        raise ValueError('OEM EAPOL critical patch requires the qualified ready object')
    send = '        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length);'
    replacement = '''        // The successful station donor uses voice TID 7 on WMM peers.
        // OEM critical-flow routing remains a separate TCL decision.
        const uint32_t normal_tid=dp.tid;
        if(f->eapol&&sta.phy.qos)dp.tid=7;
        const bool sent=dpSend(dp,{owner_io.owner,owner_io.read,owner_io.write},f->bytes,f->length,f->eapol);
        dp.tid=normal_tid;'''
    return derive(data, READY_SOURCE_SHA, [(send, replacement)])


def dp_header(data, *, single_pdev_bank=False, oem_index_bank=False):
    if sha(data) != DP_SOURCE_SHA:
        raise ValueError('OEM EAPOL critical patch requires the fixed donor Dp header')
    text = data.decode()
    if oem_index_bank and not single_pdev_bank:
        raise ValueError('OEM index bank requires the single-PDEV station')
    if single_pdev_bank:
        # The installed TB322FC module clears vdev_id_check_en on attach.
        # Keep the existing station search mode and the descriptor's VDEV ID.
        bank = 'kDpBankStation & ~kDpBankVdevCheck'
        if oem_index_bank:
            # dp_soc_init sets index mode. The OEM HAL packs MEC mode 2
            # into bank bits 22:17, with AddrX, AddrY and VDEV check clear.
            bank = 'kDpBankEncapEthernet | kDpBankIndexLookup | (2u << 17)'
        text = replace_once(
            text,
            '  write(dp, io, kDpTclBankConfig + 4 * dp.bank, kDpBankStation);',
            f'  write(dp, io, kDpTclBankConfig + 4 * dp.bank, {bank});',
            'single-PDEV station bank',
        )
    text = replace_once(
        text,
        'inline bool dpSend(Dp &dp, const ChipIo &io, const uint8_t *frame, uint32_t length)\n{\n  using namespace dpdetail;',
        'inline bool dpSend(Dp &dp, const ChipIo &io, const uint8_t *frame, uint32_t length, bool critical = false)\n'
        '{\n  using namespace dpdetail;\n'
        '  constexpr uint32_t flowOverrideEnable = 1u << 1, classifyInfoSelOne = 1u << 2, txNotifySemiHard = 3u << 8;',
        'TX encoder and critical descriptor fields',
    )
    text = replace_once(
        text,
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift);                          // a buffer, bank 0',
        '  put32(e + 8, (dp.bank & 0x3fu) << kDpTclBankShift |\n'
        '                (critical ? txNotifySemiHard : 0u));',
        'TX notify field',
    )
    text = replace_once(
        text,
        '  put32(e + 20, kDpTclTidOverwrite | (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        '  put32(e + 20, kDpTclTidOverwrite |\n'
        '                    (critical ? flowOverrideEnable | classifyInfoSelOne : 0u) |\n'
        '                    (dp.tid & 0xfu) << kDpTclTidShift | (dp.vdevId & 0xffu) << kDpTclVdevShift);',
        'critical queue fields',
    )
    return text.encode()
