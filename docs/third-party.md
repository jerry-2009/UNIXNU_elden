# Third-party snapshots

The repositories are shallow clones pinned by the commits below. They remain
separate Git repositories; edits for elden phase 1 live in
`mu_wide_platforms/Platforms/EldenPhase1Pkg` and the device DSC/FDF files.

The complete checkouts are local working dependencies and are ignored by the
main repository. The project-specific modifications are committed under
`patches/overlays/` and `drivers/`, then applied with:

```sh
python3 scripts/bootstrap_third_party.py
```

| Repository | Commit | Purpose |
| --- | --- | --- |
| `UniXNU` | `c62bf12595f9a86c1b7282cf12d5af40b441fdac` | boot manager, DarwinBoot, common drivers |
| `UniXNU-piano` | `98b3f94a067aff93a9296de7b80fdddc03dae380` | SM8750 device template and hardware results |
| `mu_wide_platforms` | `3e1d052064beb6e59cda3cfba87d50e6cc088174` | lenovo-y700g4 UEFI baseline |
| `elden-linux` | `2ea1a67cad14032e3c9c5d1c61e4ee92ad30742b` | Y700 Linux bring-up evidence |
| `UniXNU-sheng` | `251b291adf941b9953fe3ae66a808b9b626e164d` | mature UniXNU driver integration reference |
| `Project-SunUEFI` | `2d4752a1455f6448ec0d300aece28ec6eb148b20` | SM8750 firmware integration reference |

UniXNU's `drivers/DarwinBoot` submodule is initialized. The UEFI baseline's
MU/EDK II submodules are initialized by its standard stuart setup.

