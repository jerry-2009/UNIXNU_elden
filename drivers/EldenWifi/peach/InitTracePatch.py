"""Add one consolidated init return trace to the exact prepared runtime."""
import hashlib
EXPECTED={'nw_wifi.c':'a138a8cd9ab3fe22b5db0cd010e86e757439ae7be8ac9ec09733e0065ff4d22e',
          'cfg80211_core.c':'06da7a7a419ea930703b60beb85a08f9b6e52604cd84eb04d4cf2e8c2c138fbe'}
def patch(name,data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('Prepared init source differs: '+name)
    text=data.decode();original=text;edits=[]
    if name=='nw_wifi.c':
        start=text.index('int nw_wifi_start(');end=text.index('\n}',start)+2
        calls=['nw_mainline_init()','lx_init_cfg80211_init()','lx_init_ieee80211_init()','mhi_init_hook()','nw_qrtr_mhi_register()','ath12k_wifi7_pci_init()']
        variable='r'
    else:
        start=text.index('static int __init cfg80211_init(');end=text.index('\n}',start)+2
        calls=['register_pernet_device(&cfg80211_pernet_ops)','wiphy_sysfs_init()','register_netdevice_notifier(&cfg80211_netdev_notifier)','nl80211_init()','regulatory_init()']
        variable='err'
    body=text[start:end]
    for index,call in enumerate(calls):
        old=variable+' = '+call+';';assert body.count(old)==1,(name,call,body.count(old))
        marker=f' lx_log(3, "ELDEN_INIT {name}:{index+1} {call.split("(")[0]} rc=%d", {variable});'
        body=body.replace(old,old+marker,1);edits.append(marker)
    if name=='cfg80211_core.c':
        old='cfg80211_wq = alloc_ordered_workqueue("cfg80211", WQ_MEM_RECLAIM);';assert body.count(old)==1
        marker=' lx_log(3, "ELDEN_INIT cfg80211_core.c:6 workqueue rc=%d", cfg80211_wq ? 0 : -ENOMEM);'
        body=body.replace(old,old+marker,1);edits.append(marker)
    result=text[:start]+body+text[end:]
    restored=result
    for marker in edits:assert restored.count(marker)==1;restored=restored.replace(marker,'',1)
    assert restored==original
    return result.encode()
