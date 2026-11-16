# Platform reset must use the driver's shutdown callback

v170 queues MODE_OFF successfully (transaction38,52-byte IPCR frame) but sees no
UL completion, DL callback or QMI response within the existing return window.
Logical IRQs remain enabled (used/enabled1fc0ff, disabled0); the native receiver
stays enabled/unmasked, pending0/count80/error0, MHI status201. This does not prove
whether the endpoint consumed a descriptor; do not invent a firmware/clock cause.

There is an applicable upstream lifecycle distinction. Linux7.0.14
`458c6079fc1d41d564c37679c8ace02cd83ee817`, `drivers/pci/pci-driver.c`,
`pci_device_shutdown()` resumes the device then invokes `drv->shutdown(pci_dev)`;
it does not invoke remove. The exact prepared ath12k has:

- `ath12k_pci_shutdown`: clear affinity hints then
  `ath12k_pci_hw_group_power_down`, under the group mutex.
- `ath12k_pci_power_down`: restore ASPM, force wake, disable device MSI,
  stop MHI, clear INIT_DONE, then software-reset the chip.
- `ath12k_pci_remove`: unregister/clean MAC and call firmware MODE_OFF, then
  deinitialize/free the driver. This is the path currently reached by nw_wifi_stop.

Next implementation: add an explicit platform-shutdown entry to the native
runtime. Close UI/control admission, call the actual registered PCI shutdown
callback with the actual bound device, and perform real owner unbind. Keep Linux
objects and DMA backing retained until platform reset. Do not pretend this is
module unload or that MODE_OFF was acknowledged. Preserve original remove/error
cleanup for its original purpose.

After callback return the existing native code must independently observe valid
MHI reset/ready state, clear and reread bus-master, wait transaction-pending clear,
drain/mask MSI, assert owned PERST, then permit WLAN release. A missing callback,
unbind failure, config-write rejection or failed hardware check cannot report a
successful stop. Audit the actual shutdown register/config operations against
the fixed board sources; do not broadly loosen access gates or extend timeouts.

The previous successful v166 reset proof cannot substitute for a new stage4
platform-shutdown trial. Keep the full peripheral Goal and charging gaps open.

Trace caveat: qmi_txn_init returns a nonnegative allocated ID. v170's diagnostic
used `ret ? 0 : txn.id` and therefore displayed snapshot txn0; actual send/wait
records say38. Fix that observation-only expression before reuse, without
rewriting historical v170 source pins. No transport completion was observed.


v172 hardware now returns from the registered callback (unbind0/config-error0).
MHI RESET remains asserted, statusff04; the existing warm-reset check rejects it.
This is not READY. The final runtime sample is command6 (master still on);
transaction status was not read. Do not substitute the cached EP probe command2.

For the platform handoff, implement a separate host-DMA/physical-reset proof:
require the callback returned and real unbind succeeded, clear and reread PCI
bus-master against fresh identity, wait for transaction-pending clear, disable
and drain the native MSI receiver, assert/read the owned PERST low with its
existing settling bound, then allow WLAN power release. Keep all DMA backing
and tables retained to platform reset. Preserve MHI protocol reset failure in
its own status; successful physical reset must not be called warm-reset success.
Any failed or missing step still refuses release. This follows PCI handoff's
master-off requirement and adds actual reset-line proof. Do not extend waits or
merely accept a particular unrecognized MHISTATUS value.
