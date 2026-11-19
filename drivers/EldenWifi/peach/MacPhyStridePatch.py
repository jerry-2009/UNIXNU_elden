"""Port upstream4c6eb712/board26f8f87f: allocate full MAC/PHY element stride.

The protocol copy length and cap counters remain unchanged. No WMI command,
credit, descriptor, firmware or power behavior is rewritten.
"""
import hashlib

BASE='aaa6b296361c48b7407150cc79ec825bf4943f02038b022370d35975c411ca31'


def callback(text):
    start=text.index('static int ath12k_wmi_mac_phy_caps_parse(')
    return text[start:text.index('\n}\n',start)+3]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=BASE:raise ValueError('Frozen plain WMI input changed')
    text=data.decode();before=callback(text)
    old='''\tlen = min_t(u16, len, sizeof(struct ath12k_wmi_mac_phy_caps_params));
\tif (!svc_rdy_ext->n_mac_phy_caps) {
\t\tsvc_rdy_ext->mac_phy_caps = kzalloc((svc_rdy_ext->tot_phy_id) * len,
\t\t\t\t\t\t    GFP_ATOMIC);'''
    new='''\tif (!svc_rdy_ext->n_mac_phy_caps) {
\t\tsvc_rdy_ext->mac_phy_caps = kzalloc((size_t)svc_rdy_ext->tot_phy_id *
\t\t\t\t\t    sizeof(*svc_rdy_ext->mac_phy_caps),
\t\t\t\t\t    GFP_ATOMIC);'''
    if before.count(old)!=1:raise ValueError('MAC/PHY allocation anchor changed')
    after=before.replace(old,new,1)
    marker='\n\tmemcpy(svc_rdy_ext->mac_phy_caps + svc_rdy_ext->n_mac_phy_caps, ptr, len);'
    replacement='\n\tlen = min_t(u16, len, sizeof(*svc_rdy_ext->mac_phy_caps));'+marker
    if after.count(marker)!=1:raise ValueError('MAC/PHY copy anchor changed')
    after=after.replace(marker,replacement,1)
    if after.replace(replacement,marker,1).replace(new,old,1)!=before:raise ValueError('Unexpected capability-parser delta')
    return text.replace(before,after,1).encode()
