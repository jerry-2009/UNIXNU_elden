"""Reversible mode/firmware-header observations over the exact v189 WMI input."""
import hashlib

EXPECTED = "2f853ea80eec118040689a8e058d73b3dae3ac684c6e1bece012e74a09110462"


def patch(data):
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError("Mode trace WMI input differs")
    original = text = data.decode()
    changes = []

    def replace(before, after):
        nonlocal text
        if text.count(before) != 1:
            raise ValueError("Mode trace anchor differs: " + before[:80])
        text = text.replace(before, after, 1)
        changes.append((before, after))

    replace('#include "Ce3FlowTrace.h"', '#include "Ce3FlowTrace.h"\n#include "ModeTraceMeta.h"')
    before = '\tret = ath12k_wmi_cmd_send(&wmi_ab->wmi[0], skb, WMI_PDEV_SET_HW_MODE_CMDID);'
    replace(before, '''    elden_wifi_ce3_flow_note(ab, EcfWmiRequest, (u32)mode,
        ab->wmi_ab.preferred_hw_mode, EcfModeRequestMarker,
        ab->wmi_ab.svc_ext_info.num_hw_modes,
        (unsigned)ab->wmi_ab.hw_mode_info.support_dbs |
        ((unsigned)ab->wmi_ab.hw_mode_info.support_sbs << 1));
''' + before)
    before = '\tphy_map = le32_to_cpu(hw_mode_cap->phy_id_map);'
    replace(before, '''    if (len >= sizeof(*hw_mode_cap) - sizeof(hw_mode_cap->tlv_header) &&
        emt_claim(&emt_caps, 8))
        elden_wifi_ce3_flow_note(soc, EcfWmiRequest,
            le32_to_cpu(hw_mode_cap->hw_mode_id), le32_to_cpu(hw_mode_cap->phy_id_map),
            EcfFirmwareCapsMarker, le32_to_cpu(hw_mode_cap->hw_mode_config_type),
            svc_rdy_ext->arg.num_hw_modes);
''' + before)
    before = '\tpdev->hw_link_id = ath12k_wmi_mac_phy_get_hw_link_id(mac_caps);'
    replace(before, before + '''
    if (emt_claim(&emt_pdev, 4))
        elden_wifi_ce3_flow_note(ab, EcfWmiRequest, pdev->pdev_id, hw_mode_id,
            EcfFirmwarePdevMarker, le32_to_cpu(mac_caps->phy_id), supported_bands);''')
    before = '\tid = le32_get_bits(cmd_hdr->cmd_id, WMI_CMD_HDR_CMD_ID);'
    replace(before, before + '''
    if (emt_claim(&emt_events, 16))
        elden_wifi_ce3_flow_note(ab, EcfWmiRequest, id, skb->len,
            EcfFirmwareEventMarker, 0, ab->wmi_ab.preferred_hw_mode);''')
    restored = text
    for before, after in reversed(changes):
        if restored.count(after) != 1:
            raise ValueError("Mode trace is not uniquely reversible")
        restored = restored.replace(after, before, 1)
    if restored != original:
        raise ValueError("Mode trace changed an existing operation")
    return text.encode()
