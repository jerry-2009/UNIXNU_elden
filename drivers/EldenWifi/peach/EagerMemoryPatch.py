"""Keep Peach host memory capability on its original OEM wire contract."""
import hashlib

EXPECTED='4831562b8772516b52890c63c13e0ab9809da1ad708551c36cf840487c3ab205'
VENDOR='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3'
OLD='\treq.nw_on_demand_mem_valid = 1;\n\treq.nw_on_demand_mem = 1;'
NEW='''\t/* The loaded TB322FC OEM Host Capability has no TLV0x33. Do not
\t * select this prepared-source extension for Peach. Other targets retain
\t * their existing demand-memory declaration and protocol. */
\tif (ab->hw_rev != ATH12K_HW_PEACH_HW20) {
\t\treq.nw_on_demand_mem_valid = 1;
\t\treq.nw_on_demand_mem = 1;
\t}'''


def body(text):
    start=text.index('int ath12k_qmi_host_cap_send(')
    end=text.index('\n}\n',start)+3
    return text[start:end]


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Qualified host-WAKE QMI source changed')
    original=text=data.decode()
    if text.count(OLD)!=1:raise ValueError('Prepared demand-memory declaration changed')
    text=text.replace(OLD,NEW,1)
    if text.replace(NEW,OLD,1)!=original:raise ValueError('OEM host-memory change not reversible')
    return text.encode()
