> 2026-11-01 后续交付：已扩展至 P0–P3 的软件实现与离线验证，详见 IMPLEMENTATION_STATUS.md / STUDIO_OPERATIONS.md。本文 2026-10-04 的表格是历史交付状态，不代表当前配方已经通过实机质量回归。

# DELIVERY —— IAOD 生成工坊交付记录

> 2026-10-04 收官。对应 GEN_STUDIO_DEPLOY.md 的交付闭环（该文档 §6 第 8 步），但范围经主创两次扩展：从「插画生产」扩展为「通用素材工坊」，最终形态为**三管线就绪 + 视频线预备**。

## 一、交付物清单

| 管线 | 状态 | 验收证据 | 入口 |
|---|---|---|---|
| 插画（MiniMax-H3，int8/nvfp4） | ✅ 生产就绪 | P0 5 事件×3 候选零失败（`out\batch_0\` + 联络表）；14.4s/张 | `gen.ps1` / `run_batch.py` |
| 音乐（MiniMax Music 3） | ✅ 生产就绪 | 验收曲 31.7s（`out\music_0\`）；~55s/首 | `run_music.py` |
| 音效（MOSS-SoundEffect-v2.0） | ✅ 生产就绪 | 3 需求×2 变体零失败（`out\sfx_0\`）；~85s/条 | `run_sfx.py` |
| 视频（H3 I2V） | 🔶 预备待激活 | 脚本/哈希/文档齐备，**未下载增效件、未生成**（主创指令） | `seq_dl_video.ps1` → `run_video.py` |

- 权重 10 份 ~64GB 全部 sha256 验证（`models\SHA256SUMS`）；视频线 2 个待下件的哈希已写入 `seq_dl_video.ps1`，激活时自动登记
- 参数与踩坑全部存档：`workflows\*.json`（4 份）+ README §3 各小节
版权更正（2026-11-01）：H3 与 Music3 使用各自社区许可证，不能视为 Apache-2.0 或无条件商用；MOSS 单独核对 Apache-2.0。以对应版本原始许可证和授权记录为准，详见 STUDIO_OPERATIONS.md。

## 二、IAOD 侧待办（工坊不代办）

1. P0 风格验收：`out\batch_0_contact_sheet.jpg` 并排过目 → 通过后按 GEN_STUDIO_DEPLOY §4.1 批次生产 P1-P3（46 张全量）
2. 筛图规则：`out\batch_N\<event>_s<k>.png` → 人工选优 → 改名 `<event_id>.png` 放 `approved\`
3. 收货入库：IAOD 侧对话执行（`G:\IAOD\scripts\ue\import_sprint2_assets.py` 改 destination）

## 三、工坊已被实际使用

`out\` 中除部署验收批（acceptance/batch_0/music_0/sfx_0）外，另有 batch_1、music_1、music_2、music_test、sfx_1 等后续生产批——项目侧已在使用中，其 Music 3 时长实测经验已回填 README §3.4。

## 四、激活视频线（未来某天，两条命令）

```powershell
G:\vgen\scripts\seq_dl_video.ps1     # 2.5GB：音频 VAE + 8 步 turbo LoRA
# 然后 start_comfy.ps1 + run_video.py（首跑需按蓝图微调，详见 README §3.6）
```

## 五、环境终态（2026-10-04）

- 服务停止，GPU 364 MiB（低于桌面基线，无任何驻留）
- G: 剩余 511GB；E:\workflow\ComfyUI 为共享本体（v0.38.0 + 独立 venv + 3 个 custom_nodes）
- 完整使用手册：`G:\vgen\README.md`（自包含，面向项目 AI）
