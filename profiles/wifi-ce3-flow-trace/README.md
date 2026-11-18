# CE3 command and completion sequence

v188 matched the original Peach dynamic PCI window but observed R2 HP/TP0/0
and coherent DMA TP8. The original runtime reads the DMA pointer for completion;
the board sources do not establish a readable R2 mirror in shadow mode. This
profile retains the existing two R2 observations and adds one bounded sequence
of original WMI/CE operations, without changing their execution.

The exact CE and v188 WMI source hashes are required. Every insertion is uniquely
reversible to the original bytes.64 records are claimed once, published with a
release/acquire flag and dumped only at the first WMI `-EAGAIN`. Overflow saturates
its counter and never wraps/reuses a record. A partially published record is
skipped and the claimed/emitted summary exposes it. No extra MMIO reads are added.

| Kind | Metadata |
| --- | --- |
| WMI request/result | Command ID, initial buffer length, actual return code |
| PDEV selector | Parameter number and device number; no parameter value |
| CE3 post | Original slot, software HP/cached TP, byte count and DMA address |
| CE3 reap/empty | Original completion result and pointer/slot state |
| CE3 reject | Actual enqueue error and byte count |

Each record also samples the existing endpoint2 credit and credit-report counters.
Record sequence orders claims; jiffies and independent pointer/credit fields are
observations, not one atomic hardware snapshot. Packet contents, keys and radio
addresses are not recorded. The result hook never dereferences skb after sending:
a successful completion may already have freed it.

Build with `tools/build_wifi_ce3_flow_trace.py --runtime-build BASE
--parent-runtime V188 --llvm LLVM --output NEW`. The two rebuilt units are CE/WMI;
seven total runtime units differ from the original125-unit baseline,118 remain.
Use the maintained service-native/kernel/boot recipes with this explicit profile.
The supplicant/assets, native physical fence, typed return and full stock/root/
settings restoration gates remain unchanged. Retain the original90-second runtime
return condition; do not reinstate v187's premature reset.

`tools/test_wifi_ce3_flow_trace.py` executes original and derived CE send/reap bodies
and the real recorder/formatter with ASan/UBSan. HAL/MMIO/clock are modeled.
`tools/analysis/decode_wifi_ce3_flow.py` checks the captured sequence/summary and
decodes signed return values. Build, hardware and network acceptance are distinct;
this diagnostic does not itself qualify scanning or networking.

The mode-metadata variant rebuilds only WMI over v189. It uses the same64-record
ABI and adds marked request/capability/event/pdev records, separately capped at
8capabilities/4pdevs/16event headers. No parameter values or event payloads are
recorded. Capability decoding and receipt of an event do not prove that the
requested hardware-mode transition succeeded. `build_wifi_mode_trace.py` and
`decode_wifi_mode_trace.py` preserve and validate the original CE sequence.
