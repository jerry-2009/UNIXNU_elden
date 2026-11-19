"""Emit the OEM's required empty MLO array for non-MLO Peach VDEV creation.

The real loaded Peach module writes ARRAY_STRUCT/len0 even for a legacy VDEV.
Other hardware and the actual MLO case retain the original byte stream.
"""
import hashlib

EXPECTED = '0c2e215a5c0fd6e65766959b4e076b0e5db340b941000730c6ed649a24fbdbd5'


def callback(text):
    start=text.index('int ath12k_wmi_vdev_create(')
    return text[start:text.index('\n}\n',start)+3]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:
        raise ValueError('Expected the retained full-stride WMI source')
    original=data.decode(); before=callback(original); after=before
    marker='\tbool is_ml_vdev = is_valid_ether_addr(args->mld_addr);'
    if after.count(marker)!=1:
        raise ValueError('VDEV legacy selector changed')
    after=after.replace(marker,marker+
        '\n\tbool empty_mlo = !is_ml_vdev && ar->ab->hw_rev == ATH12K_HW_PEACH_HW20;',1)
    marker='\t\t(is_ml_vdev ? TLV_HDR_SIZE + sizeof(*ml_params) : 0);'
    if after.count(marker)!=1:
        raise ValueError('VDEV allocation length changed')
    after=after.replace(marker,
        '\t\t(is_ml_vdev ? TLV_HDR_SIZE + sizeof(*ml_params) :\n\t\t empty_mlo ? TLV_HDR_SIZE : 0);',1)
    marker='\tath12k_dbg(ar->ab, ATH12K_DBG_WMI,\n\t\t   "WMI vdev create:'
    if after.count(marker)!=1:
        raise ValueError('VDEV trailing-array boundary changed')
    addition='''\tif (empty_mlo) {
\t\ttlv = ptr;
\t\ttlv->header = ath12k_wmi_tlv_hdr(WMI_TAG_ARRAY_STRUCT, 0);
\t}

'''
    after=after.replace(marker,addition+marker,1)
    restore=after.replace(addition,'',1).replace(
        '\t\t(is_ml_vdev ? TLV_HDR_SIZE + sizeof(*ml_params) :\n\t\t empty_mlo ? TLV_HDR_SIZE : 0);',
        '\t\t(is_ml_vdev ? TLV_HDR_SIZE + sizeof(*ml_params) : 0);',1).replace(
        '\n\tbool empty_mlo = !is_ml_vdev && ar->ab->hw_rev == ATH12K_HW_PEACH_HW20;','',1)
    if restore!=before:
        raise ValueError('Unexpected VDEV delta')
    return original.replace(before,after,1).encode()
