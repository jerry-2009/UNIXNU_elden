/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
/* Original stock firmware fingerprints, no firmware bytes or device identifiers. */
static const struct {const char *path;unsigned bytes;const char *sha256;} elden_wifi_firmware_inputs[]={
    {"image/peach/amss20.bin",6959168,"848a2f049ccfcdf4831a3983b19e2956830d094cf62c0e257f5ded4ed31120c1"},
    {"image/peach/phy_ucode20.elf",290816,"092f97c96cec23892f32d5f0db0858ba49312c0592f35bb2e60299e30055d452"},
    {"image/peach/aux_ucode20.elf",61440,"7b9bbb9bb6d1df0fb39d8067d9829f5ec096f06c9af9d7d6e2e6d28b194f1206"},
    {"image/tmel_peach_20.elf",56752,"a175c8d9d0e6b38b5ae23ff0175da795b14b8268919463d2b6e1cb2bfeebc9f8"},
    {"image/peach/data20.msc",1812314,"ee6a685014b02a7cc5ab48692e52cfce67145ad995183cac8b30acd27800c8fe"},
    {"image/peach/regdb.bin",24278,"84b55a5691d02b78b96face90b2ba69718a2e617434ffb888a4943b9d2ada5a5"},
    {"image/peach/bdwlan.elf",125420,"c6f861550a711335e682df1c8be4a0384ba361d560225c06da23e32de014a19e"},
    {"image/peach/qdss_trace_config_v2.cfg",6237,"94251904525f36f69092db8abde1f5198bd32c8c5fa482448e7076e0e3bc0eab"},
};
