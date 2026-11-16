"""Reversible metadata tracing for the shutdown QMI transaction and IRQs."""
HEADER='#include "EldenQmiTrace.h"\n'
ARRAY='volatile uint64_t elden_wifi_qmi_trace[EldenQmiTraceCount]={0};\n'
IRQ='''
/* No pointer traversal or interrupt state changes: the table has64 fixed slots. */
void elden_wifi_irq_trace(uint32_t base,uint32_t masks[5]) {
  for (unsigned i=0;i<5;i++) masks[i]=0;
  for (unsigned i=0;i<64;i++) {
    unsigned used=READ_ONCE(g_irq[i].used),irq=READ_ONCE(g_irq[i].irq);
    if (!used || irq<base || irq-base>=32) continue;
    uint32_t bit=1u<<(irq-base);masks[0]|=bit;
    if (!READ_ONCE(g_irq[i].disabled)) masks[1]|=bit;else masks[4]|=bit;
    if (READ_ONCE(g_irq[i].pending)) masks[2]|=bit;
    if (READ_ONCE(g_irq[i].strict)) masks[3]|=bit;
  }
}
'''
def patch(name,data):
    original=data.decode();text=original;changes=[]
    def change(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('QMI trace anchor differs: '+old[:100])
        text=text.replace(old,new,1);changes.append((new,old))
    if name=='qmi.c':
        start=text.index('static int ath12k_qmi_wlanfw_mode_send(');end=text.index('\n}',start)+2
        body=text[start:end];new=body
        def insert(old,tail):
            nonlocal new
            if new.count(old)!=1:raise ValueError('Mode trace anchor differs')
            new=new.replace(old,old+tail,1)
        insert('\treq.mode = mode;','''
    if (mode == ATH12K_FIRMWARE_MODE_OFF) {
        for (unsigned i=0;i<EldenQmiTraceCount;i++) __atomic_store_n(&elden_wifi_qmi_trace[i],0,__ATOMIC_RELAXED);
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiActive],1,__ATOMIC_RELEASE);
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiPhase],1,__ATOMIC_RELAXED);
        lx_log(3,"ELDEN_QMI_MODE begin mode=%u",mode);
    }''')
        insert('qmi_wlanfw_wlan_mode_resp_msg_v01_ei, &resp);','''
    if (mode == ATH12K_FIRMWARE_MODE_OFF) {
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiTxn],ret?0:txn.id,__ATOMIC_RELAXED);
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiPhase],2,__ATOMIC_RELAXED);
        lx_log(3,"ELDEN_QMI_MODE init=%d txn=%u",ret,ret?0:txn.id);
    }''')
        insert('qmi_wlanfw_wlan_mode_req_msg_v01_ei, &req);','''
    if (mode == ATH12K_FIRMWARE_MODE_OFF) {
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiPhase],3,__ATOMIC_RELAXED);
        lx_log(3,"ELDEN_QMI_MODE send=%d txn=%u",ret,txn.id);
    }''')
        old='\tret = qmi_txn_wait(&txn, msecs_to_jiffies(ATH12K_QMI_WLANFW_TIMEOUT_MS));'
        before='''    if (mode == ATH12K_FIRMWARE_MODE_OFF) {
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiPhase],4,__ATOMIC_RELAXED);
        lx_log(3,"ELDEN_QMI_MODE wait txn=%u timeout-ms=%u",txn.id,ATH12K_QMI_WLANFW_TIMEOUT_MS);
    }
'''
        after='''
    if (mode == ATH12K_FIRMWARE_MODE_OFF) {
        __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiPhase],5,__ATOMIC_RELAXED);
        lx_log(3,"ELDEN_QMI_MODE returned=%d result=%u error=%u",ret,resp.resp.result,resp.resp.error);
    }'''
        if new.count(old)!=1:raise ValueError('Mode wait differs')
        new=new.replace(old,before+old+after,1);change(body,new)
    elif name=='nw_qrtr_mhi.c':
        change('static void dl_cb(struct mhi_device *d, struct mhi_result *r) {','''static void dl_cb(struct mhi_device *d, struct mhi_result *r) {
  if (__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiActive],__ATOMIC_ACQUIRE)) {
    uint64_t n=__atomic_add_fetch(&elden_wifi_qmi_trace[EldenQmiDlDone],1,__ATOMIC_RELAXED);
    __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiDlStatus],(uint64_t)(int64_t)r->transaction_status,__ATOMIC_RELAXED);
    if(n<=8)lx_log(3,"ELDEN_QMI_DL done=%llu status=%d bytes=%llu",(unsigned long long)n,r->transaction_status,(unsigned long long)r->bytes_xferd);
  }''')
        change('static void ul_cb(struct mhi_device *d, struct mhi_result *r) { (void)d;','''static void ul_cb(struct mhi_device *d, struct mhi_result *r) { (void)d;
  if (__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiActive],__ATOMIC_ACQUIRE)) {
    uint64_t n=__atomic_add_fetch(&elden_wifi_qmi_trace[EldenQmiUlDone],1,__ATOMIC_RELAXED);
    __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiUlStatus],(uint64_t)(int64_t)r->transaction_status,__ATOMIC_RELAXED);
    if(n<=8)lx_log(3,"ELDEN_QMI_UL done=%llu status=%d bytes=%llu",(unsigned long long)n,r->transaction_status,(unsigned long long)r->bytes_xferd);
  }''')
        old='  int rc = mhi_queue_buf(e->dev, DMA_TO_DEVICE, b, len, MHI_EOT);'
        change(old,old+'''
  if (__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiActive],__ATOMIC_ACQUIRE)) {
    uint64_t n=__atomic_add_fetch(&elden_wifi_qmi_trace[EldenQmiQueued],1,__ATOMIC_RELAXED);
    if(n<=8)lx_log(3,"ELDEN_QMI_UL queue=%llu status=%d bytes=%llu",(unsigned long long)n,rc,(unsigned long long)len);
  }''')
    elif name=='qmi_interface.c':
        change('\thdr = buf;','''\thdr = buf;
    if (__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiActive],__ATOMIC_ACQUIRE)) {
        uint64_t n=__atomic_add_fetch(&elden_wifi_qmi_trace[EldenQmiResponses],1,__ATOMIC_RELAXED);
        if(n<=8)lx_log(3,"ELDEN_QMI_RX type=%u txn=%u msg=%u bytes=%llu",hdr->type,le16_to_cpu(hdr->txn_id),le16_to_cpu(hdr->msg_id),(unsigned long long)len);
    }''')
        change('\t\t\tcomplete(&txn->completion);','''            if (__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiActive],__ATOMIC_ACQUIRE) && txn->id==__atomic_load_n(&elden_wifi_qmi_trace[EldenQmiTxn],__ATOMIC_RELAXED)) {
                __atomic_add_fetch(&elden_wifi_qmi_trace[EldenQmiCompleted],1,__ATOMIC_RELAXED);
                __atomic_store_n(&elden_wifi_qmi_trace[EldenQmiResult],(uint64_t)(int64_t)ret,__ATOMIC_RELAXED);
                lx_log(3,"ELDEN_QMI_RX complete txn=%u decode=%d",txn->id,ret);
            }
\t\t\tcomplete(&txn->completion);''')
    elif name!='lx_rt.c':raise ValueError('Unknown QMI trace source')
    recovered=text
    for new,old in reversed(changes):
        if recovered.count(new)!=1:raise ValueError('QMI trace not reversible')
        recovered=recovered.replace(new,old,1)
    if recovered!=original:raise ValueError('Original QMI semantics changed')
    return (HEADER+(ARRAY if name=='qmi.c' else '')+text+(IRQ if name=='lx_rt.c' else '')).encode()
