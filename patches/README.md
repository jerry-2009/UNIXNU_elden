# Upstream overlays

`third_party/` contains upstream checkouts and is intentionally not committed.
This directory stores the small set of files required to reproduce the elden
phase-1 integration on top of the pinned revisions listed in
[`../docs/third-party.md`](../docs/third-party.md).

## Layout

| Overlay | Pinned base | Purpose |
| --- | --- | --- |
| `overlays/UniXNU/` | `c62bf12595f9a86c1b7282cf12d5af40b441fdac` | libfdt compatibility and UniXNULib package wiring |
| `overlays/mu_wide_platforms/` | `3e1d052064beb6e59cda3cfba87d50e6cc088174` | lenovo-y700g4 FV/DSC wiring, Android v3 header size, and patched PMIC binary |
| `../drivers/EldenRamDiskDxe/` | `3e1d052064beb6e59cda3cfba87d50e6cc088174` | read-only FAT payload block driver copied into `EldenPhase1Pkg` |

Verify that an existing local `third_party/` checkout contains this project's
changes:

```sh
python3 scripts/bootstrap_third_party.py --verify-only
```

Reapply the overlays from the committed source of truth:

```sh
python3 scripts/bootstrap_third_party.py
```

On a fresh checkout, clone the two build dependencies and apply the overlays in
one step:

```sh
python3 scripts/bootstrap_third_party.py --clean-build-deps
```
