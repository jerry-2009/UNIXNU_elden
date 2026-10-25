# SM8750 transition profile

UniXNU does not currently publish an `UniXNU-sm8750-common` repository.
This directory follows the same `soc.toml`, `configs/`, `dts/` and
`patches/xnu/series` layout as the official SM8550 common profile so the
format 2 device configuration can be parsed and validated.

The DTSI contains only the shared CPU topology, PSCI conduit and GICv3
resources needed by the first XNU milestone. UFS, display and touch platform
operations remain device work and are not claimed here.

Before release, move these files to a reviewed `UniXNU-sm8750-common`
repository, pin its commit in `feeds.toml`, and remove this local fallback.
