/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Append-only observer for Ath12kWifi5f7f5a8 shim/src/lx_rt.c.
 * Called on its owning wireless worker, never from a native IRQ callback.
 * No IRQ acknowledgement, register write, work dispatch or pointer traversal.
 */
void elden_wifi_irq_snapshot(uint32_t base,uint32_t words[10]) {
  for (unsigned i=0;i<10;i++) words[i]=0;
  for (unsigned i=0;i<64;i++) {
    unsigned used=READ_ONCE(g_irq[i].used),irq=READ_ONCE(g_irq[i].irq);
    if (!used || irq<base || irq-base>=32) continue;
    uint32_t bit=1u<<(irq-base);words[0]|=bit;
    if (!READ_ONCE(g_irq[i].disabled)) words[1]|=bit;else words[4]|=bit;
    if (READ_ONCE(g_irq[i].pending)) words[2]|=bit;
    if (READ_ONCE(g_irq[i].strict)) words[3]|=bit;
    if (is_running(&g_irq[i])) words[5]|=bit;
  }
  words[6]=(uint32_t)g_depth;words[7]=(uint32_t)g_nrunning;
  words[8]=__atomic_load_n(&mutexes_held,__ATOMIC_ACQUIRE);
  words[9]=(uint32_t)g_irq_polling;
}
