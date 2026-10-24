# 阶段 0：资产与恢复路径

状态：**已完成（2026-10-25）**

本阶段只确认恢复能力，不执行设备写入。恢复资产由设备所有者确认；自动化脚本
不搜索、不枚举、也不记录备份位置。

## 完成条件

| 条件 | 状态 | 证据 |
| --- | --- | --- |
| 可通过 9008 进入恢复路径 | 已确认 | `configs/phase0-assets.json` |
| 有已知可用的恢复包 | 已确认 | `configs/phase0-assets.json` |
| 有全量固件备份 | 已确认 | `configs/phase0-assets.json` |
| 回滚不依赖实验性启动链 | 已确认 | 恢复资产独立于 UniXNU |
| 启动由设备所有者本人执行 | 已确认 | `configs/phase0-assets.json` |
| 后续测试限于 RAM 启动 | 已规定 | `configs/phase0-assets.json` |
| 启动镜像来源与哈希可追溯 | 已规定 | 人工测试记录 |

备份路径不属于验收内容，也不会写入仓库。

## 阶段 1 入口

阶段 1 的每次设备启动都由设备所有者本人操作。Codex 不代跑启动命令，也不创建
启动队列或后台监视。设备所有者每次手工记录镜像 SHA-256、构建来源和测试时间；
同一镜像至少两次 RAM 启动结果一致后，才继续后续调试。

严禁通过任何其他 fastboot 入口执行 `flash`、`set_active`、`erase`、`format`、
`delete-logical-partition`、`create-logical-partition` 或分区/GPT 写操作。
