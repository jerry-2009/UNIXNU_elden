/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Fixed TB322FC Linux6f97250e: DesignWare group0, SPI141 = GIC INTID173. */
enum { EldenMsiIntid=173,EldenMsiAddrLo=0x820,EldenMsiAddrHi=0x824,
       EldenMsiEnable=0x828,EldenMsiMask=0x82c,EldenMsiStatus=0x830 };
enum { EldenMsiIdle,EldenMsiWorking,EldenMsiPrepared,EldenMsiArmed,EldenMsiStopped,EldenMsiRefused,EldenMsiHeld };
typedef struct {
    void *context;
    int (*admit)(void *); /* actual root/power epoch + owned DMA, thread context */
    int (*quiesced)(void *); /* real DMA/MHI stopped; never infer from arena live0 */
    int (*read)(void *,uint32_t offset,uint32_t *); /* held DBI, IRQ-safe */
    int (*write)(void *,uint32_t offset,uint32_t); /* IRQ-safe, ordered/W1C */
    int (*attach)(void *,uint32_t intid,void(*)(void *),void *cookie,uint32_t *flags,uint64_t *router);
    int (*mask_irq)(void *,uint32_t intid,bool);
    void (*wake)(void *); /* IRQ-safe: queue/wake only, no firmware dispatch */
    uint64_t (*now_us)(void *);
    void (*delay_us)(void *,unsigned);
} EldenPcieMsiIo;
typedef struct {
    EldenPcieMsiIo io;
    uint64_t target,affinity;
    unsigned state,stage,writes;
    int error,stop_result;
    bool controls_started,attached,stop_attempted;
    /* IRQ-shared fields are accessed atomically. Keep the cookie/maps/power
     * alive until reset, including after a refused or timed-out stop. */
    unsigned irq_access,irq_calls,pending,irq_count,empty_count;
    int irq_error;
} EldenPcieMsi;
/* One serialized owner configures/stops. No endpoint capability or bus-master
 * writes here. Prepared/Armed means receiver setup, not a device MSI result. */
int elden_pcie_msi_prepare(EldenPcieMsi *,uint64_t owned_sink_iova,uint64_t boot_affinity);
int elden_pcie_msi_arm(EldenPcieMsi *);
uint32_t elden_pcie_msi_pending(EldenPcieMsi *);
int elden_pcie_msi_stop(EldenPcieMsi *,uint64_t deadline_us);
#ifdef __cplusplus
}
#endif
