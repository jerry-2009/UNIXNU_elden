# v165 consolidated initialization trace

Diagnostic derivative of v164. `InitTracePatch.py` adds return-value logging
after the six `nw_wifi_start` init calls and the cfg80211 init substeps. Removing
the exact inserted statements restores both original prepared sources byte for
byte. No init return, branch, register, firmware or power policy is changed.

Two C units were rebuilt with the original headers; the reviewed PCI lifecycle
unit and 122 other objects remain. Native/kernel linking, 30 original Apple
executable regions, entry relation and direct-call checks pass. Menu arguments
remain identical to v164 (1,023 bytes), including default/countdown/recovery.

- Kernel: `255707dba4e21f3aef596bd988666541e444ddd3141f42c9259892d515519439`.
- Signed boot: `4ae415a0d7e0d627a54e98a71b77585ad4c287c99f887df6183321bece1a2e12`.
- Session: `080a6e18406e8a9e`; rollback/footer/parent `1738713600/0/3`.
- 175 kernel source inputs match; full static boot audit passed.

Hardware validation is pending at this commit. The diagnostic is to locate
v164's initialization error `-16`; it is not a claimed fix or new hardware
acceptance. Workbench outputs are `edl_work/wifi-init-v165-20261116` and
`edl_work/wifi-init-boot-v165-20261116/package1`; corresponding Mac directories
are under `lab/`. The initial source anchor caught `register` inside the cleanup
name `unregister` and refused; explicit assignment anchors fixed runtime2.
