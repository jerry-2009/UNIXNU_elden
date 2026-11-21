/* Diagnostic metadata only: never copy or log QMI/EAPOL/key payloads. */
#pragma once
#include <stdint.h>
enum { EldenQmiActive,EldenQmiTxn,EldenQmiQueued,EldenQmiUlDone,EldenQmiUlStatus,
       EldenQmiDlDone,EldenQmiDlStatus,EldenQmiResponses,EldenQmiCompleted,
       EldenQmiResult,EldenQmiPhase,EldenQmiTraceCount };
#ifdef __cplusplus
extern "C" {
#endif
extern volatile uint64_t elden_wifi_qmi_trace[EldenQmiTraceCount];
void elden_wifi_irq_trace(uint32_t base,uint32_t masks[5]);
#ifdef __cplusplus
}
#endif
