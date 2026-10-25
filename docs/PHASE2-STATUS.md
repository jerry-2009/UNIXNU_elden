# 阶段 2 主机验证状态

更新时间：2026-10-25

状态：**主机构建与静态校验通过；尚未实机 RAM 启动。**

## 输入

| 输入 | 值 |
| --- | --- |
| 预链接内核 | `kernel.macho`，51,806,208 字节 |
| 内核 SHA-256 | `6912319adf0b623eb04987f2dbd29c4b5c9f97ca18b469571bd67c7815c86c07` |
| 来源工件 | [UniXNU-piano Run #23](https://github.com/code002-2/UniXNU-piano/actions/runs/39403317018) `piano-kernel` |
| 工件 ZIP SHA-256 | `87be3e891b25a6af894fec6e37c2134bbba1c30d77fe9bb9be8c8c1bc9cde6f6` |
| UniXNU | `16e592abee8a550dec8154ed1f38b5ebc4f16213` 的格式 2 和共享 RAM-disk 驱动 |
| Mu-Silicium | `3e1d052064beb6e59cda3cfba87d50e6cc088174` |

公开产物只用于主机验证，不提交到仓库。正式设备构建仍需要固定的
kernelcache/ABI 输入和设备自己的 `unique-chip-id`。

## 构建结果

主机验证构建使用随机测试种子，因此产物**不是设备可用镜像**。重新运行：

```sh
python scripts/build_phase2.py \
  --kernel .cache/elden-kernel-6912319a/kernel.macho \
  --unique-chip-id "$(openssl rand -hex 8)" \
  --test-seed \
  --crypto-path "$PWD/.cache/phase1/basecrypto"
```

最近一次主机测试种子构建的产物：

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| `out/elden-phase2.dtb` | 1,557 | `60316b6d4e753610610126d691f6d39ba54edd21e9b02875ec034e81e27a4371` |
| `out/elden-phase2-payload.img` | 67,108,864 | `ecffe65ae40506e3d889b4a9ec605a200044d28279f1511a08e421cb34bd51c4` |
| `out/SILICIUM_UEFI-phase2.fd` | 4,194,304 | `7492f11c6acb02e79bbb1cc8f9ecb6adcad9b9431f8644a93441a777ebabe7d5` |
| `out/elden-phase2.img` | 69,795,840 | `0eeb3909f45425d339f3f06840e6348408569ea80ad2ffdb943432c735642000` |

注意：`out/elden-phase2.img` 产生于加入显式 `--test-seed` 标记之前，但确实
使用了主机随机种子。下一次带 `--test-seed` 的构建会在
`out/phase2-build.json` 中写入 `device_ready: false`。

## 校验范围

`scripts/verify_phase2_artifact.py` 已确认：

- Android 启动头为 v3，ramdisk 大小为 67,108,864 字节；
- ramdisk 与生成的 FAT 载荷逐字节一致；
- boot kernel 解压后等于 BootShim 加 4 MiB FD，并携带合法 DTB；
- FD 包含 `UniXNURamDiskDxe`、`UniXNU`、`UniXNUDxe` 和 `DarwinBoot`；
- FD 不包含 `EldenRamDiskDxe`、阶段 1 内嵌载荷或 `UFSDxe`；
- 载荷内 `kernel.macho` 与记录的预链接内核逐字节一致；
- 载荷内存在 13,068 字节的 ADT sidecar，`unixnu.toml` 包含 `xnu` 启动项。

## 未验证

- ABL 是否在 `fastboot boot` 时保留完整 64 MiB ramdisk 及其地址；
- `UniXNURamDiskDxe` 是否从本机 FDT 成功发布该卷；
- UniXNU 菜单是否显示 XNU 项并进入 DarwinBoot；
- DarwinBoot、XNU 入口、平台专家和任何硬件 provider；
- trust cache、Data seed、UFS、显示和触摸。

设备所有者只应使用 `fastboot boot out/elden-phase2.img`，同一镜像至少完成
两次 RAM 冷启动并记录整机可见结果。

## 下一步

1. 使用设备自己的 `unique-chip-id` 重建，不传 `--test-seed`。
2. 先做一次 RAM 启动，确认 `UNIXNURAMDISK` 和 DarwinBoot 输出。
3. 若进入 DarwinBoot，记录内核地址、framebuffer 参数和第一个 panic 或
   provider 缺失点。
4. 对照设备 live FDT 补齐真实保留区、UFS、显示和触控节点。
