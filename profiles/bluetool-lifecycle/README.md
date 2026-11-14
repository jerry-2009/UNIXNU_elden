# v127 BlueTool lifecycle cache integration

This integrates the signed four-field cache prepared by
[build_bluetool_job_cache.py](../../tools/build_bluetool_job_cache.py).
The other560 jobs, cache top-level entries, helper binary and native17 routing
remain unchanged. The new cache and detached signature are embedded once each.
One new exact cache CDHash joins the old trust modules.

`LaunchCache.inc` writes only the two compiled files below the fresh volatile
Data directory. It enforces a1MiB cap, exclusive/no-follow creation, exact mount
identity, mode0444/root ownership, explicit final length, fsync and complete
readback. The original131072B IconServices writer is unchanged. The cache then
mounts as a read-only union over /System/Library/xpc, with another full content,
mode and ownership check. Failure unwinds the cache mount and the outer helper
mount; runtime readiness is published only after both succeed.

The actual writer passes27 ASan/UBSan cases for both fixed files, null/wrong
mount, type/read-only errors, exclusive creation, short/failed writes,
metadata/fsync/readback/owner/close failures. This host test uses filesystem
doubles; actual mount/readback is separately observed on the tablet.

One kern_exec object is rebuilt over the v125 native transport baseline,
retaining its two phase observers and omitting v126's finer syscall observers.
The source overlay is closed; the other linked inputs, exports and30 original
Apple executable ranges are checked. The added cache moves the entry return to
0xfffffff0075b205c; the same startup assembly object/word and7124-byte relative
contract qualify the relocation. Native code for the changed unit is scalar.

From declared source-build inputs:

```sh
python3 -B tools/build_clean.py --variant bluetooth --bt-exit-stack \
  --software-keystore --bluetool-launch --bt-transport-trace \
  --bluetool-lifecycle --inputs inputs.json --output NEW --target boot
```

This generates the cache from the original OS input itself. It does not require
an old v99 or private runtime directory. The full baseline and incremental stages
have each been run; the complete combined flags have not been rerun from empty
output. Direct integration uses `tools/build_bluetool_lifecycle.py` with the clean
output, transport output and cache output produced by those tools.

Boot0b964a78b778652e74cd1788388325a92951b0c395eb2f0cec0432a381f5ff09,
sessiona44777f0fc54bba3; floor1738713600/footer0/parent3 unchanged.

## Hardware

Both trials reach `ELDEN_BT_CACHE stage=5 status=0 bytes=925323` and runtime
prepared1. Thus the mounted content/readback integration succeeds. The later
stall remains: bootstrap Ready/0 is recorded, no H4 connection is captured.

The first capture is114763B/drop23 then a host status-write timeout. A second
trial uses the exact same image and a receive-only logger, with no status queries
or RPC commands. It also stops producing bytes at110710B while the receiver
remains open until reset. Its kernel drop count is unavailable, not zero. This
rules out periodic PC status writes as a necessary trigger; it does not identify
whether the device's kernel, userland or USB path stopped progressing.

Both automatically return to physical fastboot, with exact reset cause
unproven/no sync-return confirmation. Full stock SHA restoration and Android
root/green/boot completion pass, then sleep is requested. Neither image is a
working Bluetooth or new default GUI baseline. See hardware-result.json.

Static sysent review confirms socket97/connect98/ioctl54 point to their matching
functions in both v126 native/prelinked outputs and v127. It does not prove live
invocation or acceptance by the trace's process-identity filter. Next review the
actual BlueTool/XPC completion and native17 startup path, without more blind
kernel probes or re-tuning proven WCN firmware/power.
