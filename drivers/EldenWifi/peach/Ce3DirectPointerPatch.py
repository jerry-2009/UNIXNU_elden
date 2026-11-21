"""Contrast CE3 shadow notification with the original direct-HP implementation.

The OEM hal_srng_setup(ignore_shadow) and Linux's existing no-shadow branch
use this actual R2 address. Limit the contrast to the owned Peach CE3 source;
do not alter QMI shadow tables, CE2, other rings, credits or descriptors.
"""
import hashlib

EXPECTED='08ad25eb9e2ddace5502a97207f1c89dbd9e404bef45cdd63e40086ee19c0b4e'


def callback(text):
    start=text.index('void ath12k_wifi7_hal_set_umac_srng_ptr_addr(')
    return text[start:text.index('\n}\n',start)+3]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:
        raise ValueError('Expected exact frozen wifi7 HAL input')
    original=data.decode();old=callback(original)
    marker='\tu32 reg_base = srng->hwreg_base[HAL_SRNG_REG_GRP_R2];'
    if old.count(marker)!=1:raise ValueError('Original R2 pointer source changed')
    addition='''
\tif (ab->hw_rev == ATH12K_HW_PEACH_HW20 &&
\t    srng->ring_id == HAL_SRNG_RING_ID_CE0_SRC + 3 &&
\t    srng->ring_dir == HAL_SRNG_DIR_SRC &&
\t    reg_base == 0x01b86400U) {
\t\t/* The existing direct branch; OEM calls this ignore_shadow. */
\t\tsrng->u.src_ring.hp_addr = (u32 *)((unsigned long)ab->mem + reg_base);
\t\tath12k_warn(ab, "ELDEN_CE3_DIRECT selected=1 hp-offset=%x; CE3 only\\n",
\t\t\t    reg_base);
\t\treturn;
\t}
'''
    new=old.replace(marker,marker+addition,1)
    if new.replace(addition,'',1)!=old:raise ValueError('Unexpected direct-pointer delta')
    return original.replace(old,new,1).encode()
