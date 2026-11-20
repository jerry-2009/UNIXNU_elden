/* SPDX-License-Identifier: GPL-2.0-only */
/* Read existing, owned WCN mappings. These samples are not atomic snapshots. */
static int board_state(unsigned stage)
{
    if (stage != 12 && stage != 9 && stage != 90) return -22;
    if (ml_at_interrupt_context()) return -19;
    Context *c = __atomic_load_n(&active, __ATOMIC_ACQUIRE);
    uint64_t epoch = __atomic_load_n(&wlan_epoch, __ATOMIC_ACQUIRE);
    if (!c || !epoch || !c->sideband.ready || !c->sideband_maps[0].va ||
        !c->sideband_maps[1].va || !c->sideband_maps[2].va ||
        __atomic_load_n(&platform_stopping, __ATOMIC_ACQUIRE)) return -19;
    int rc = platform_enter();
    if (rc) return rc;
    uint32_t pins[4][3] = {};
    EldenWcnRailState power[EldenWcnRailCount] = {};
    unsigned pin_reads = 0, rail_reads = 0;
    rc = elden_wcn_shared_check(&c->shared, EldenWcnWlan, epoch);
    for (unsigned i = 0; !rc && i < 4; ++i) {
        Region *map = i == 0 ? &c->wlan : &c->sideband_maps[i - 1];
        for (unsigned j = 0; !rc && j < 3; ++j) {
            pins[i][j] = map->read(j * 4);
            ++pin_reads;
            if (pins[i][j] == UINT32_MAX) rc = -5;
        }
    }
    for (unsigned i = 0; !rc && i < EldenWcnRailCount; ++i) {
        rc = rail_read(c, (EldenWcnRail)i, &power[i]);
        if (!rc) ++rail_reads;
    }
    uint32_t main = 0, even = 0;
    if (!rc) rc = parents(c, &main, &even);
    if (!rc && epoch != __atomic_load_n(&wlan_epoch, __ATOMIC_ACQUIRE)) rc = -11;
    if (!rc) rc = elden_wcn_shared_check(&c->shared, EldenWcnWlan, epoch);
    platform_leave();
    static const unsigned gpios[] = {16, 18, 19, 202};
    log("\nELDEN_BOARD_STATE stage=%u rc=%d epoch=%llu pins=%u rails=%u parent=%u/%u; existing-reads-only non-atomic\n",
        stage, rc, (unsigned long long)epoch, pin_reads, rail_reads, main, even);
    for (unsigned i = 0; i < 4 && i * 3 + 3 <= pin_reads; ++i)
        log("\nELDEN_BOARD_PIN stage=%u gpio=%u ctl=%x io=%x irq=%x\n",
            stage, gpios[i], pins[i][0], pins[i][1], pins[i][2]);
    for (unsigned i = 0; i < rail_reads; ++i)
        log("\nELDEN_BOARD_RAIL stage=%u rail=%u mv=%u mode=%x en=%x status=%x target=%u\n",
            stage, i, power[i].mv, power[i].mode, power[i].enable,
            power[i].status, c->power.target[i]);
    return rc;
}
