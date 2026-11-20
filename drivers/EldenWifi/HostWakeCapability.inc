/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* CNSS obtains the actual WAKE MSI assignment before publishing host caps. */
static int elden_wifi_host_wake_capability(struct ath12k_base *ab,
    struct qmi_wlanfw_host_cap_req_msg_v01 *req)
{
    if (!ab || !req) return -EINVAL;
    if (ab->hw_rev != ATH12K_HW_PEACH_HW20) return 0;
    if (!ab->hif.ops || !ab->hif.ops->get_user_msi_vector) return -ENODEV;
    int vectors = 0;
    u32 data = 0, base = 0;
    int rc = ab->hif.ops->get_user_msi_vector(ab, "WAKE", &vectors, &data, &base);
    if (rc) return rc;
    /* This profile owns all 32 endpoint vectors; WAKE is the single vector13.
     * Use callback data, not the native IRQ number or a fabricated alias. */
    if (vectors != 1 || base != 13 || data > 31 || data < base) return -EINVAL;
    if (req->wake_msi_valid) return req->wake_msi == data ? 0 : -EBUSY;
    req->wake_msi = data;
    req->wake_msi_valid = data != 0;
    ath12k_warn(ab, "ELDEN_HOST_WAKE_CAP wake-msi=%u vectors=%d base=%u valid=%u; callback-derived\n",
        data, vectors, base, req->wake_msi_valid);
    return 0;
}
