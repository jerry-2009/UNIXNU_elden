# Earlier core/UFS-only2GiB diagnostic

This profile replaced the core/UFS size checks but omitted the independently
archived software KeyStore adapter. v180/v181 mounted Data and then refused
KeyStore startup; it is retained for diagnosis, not the current GUI candidate.

Use [data-capacity-2g-key](../data-capacity-2g-key/README.md), which rebuilds the
actual adapter. This directory retains the original seed fingerprint and shared
layout/source contracts; default512MiB behavior remains explicit and unchanged.
