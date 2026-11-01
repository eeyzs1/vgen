# IAOD 生成工坊部署与插画生产交接（GEN_STUDIO_DEPLOY）

> **写给谁：** 在 `G:\vgen\` 新对话里接手「部署生成环境 + 生产事件插画」的 AI agent（或主创本人跟着做）。
> **本文自包含：** 不需要原对话上下文；上游背景如需深挖去读 `G:\IAOD\HANDOFF.md` 的「冲刺2/3」段。
> **日期：** 2026-10 · **任务owner：** 主创（部署对话执行，IAOD 侧对话收图入库）

---

## 0. 一句话任务

在本机部署 ComfyUI + MiniMax-H3（量化版），为游戏《星际大航海》批量生成**事件插画**（第一批 14 张样图起步，总量约 60 张），风格统一、命名与事件 id 对齐，成品放 `approved\` 目录等 IAOD 侧收货。

---

## 1. 背景（为什么做）

- 游戏：单机回合制 Roguelike 星球探险，UE 5.7，仓库 `G:\IAOD`。
- 2026-10 内容冲刺已完成「三段式遭遇事件」系统（情境文本→选择→后果文本，46 条世界事件 + 7 条休息事件），但**事件弹窗目前只有肖像+章色，没有插画**——这是艺术表达的最大缺口。
- 插画补齐后由 IAOD 侧挂进「勘测局档案卡」弹窗（UI 管线已就绪，入库脚本已有）。
- 主创选定工具路线：**MiniMax-H3**（社区有 8GB 显存实战方案；备选 Z-Image-Turbo）。

## 2. 本机事实（已核实）与待填项

| 项 | 值 |
|---|---|
| 系统 | Windows（PowerShell 可用） |
| 磁盘空闲 | C: 1643GB · E: 631GB · F: 1169GB（勿动，DSH 工具盘）· **G: 623GB（推荐用）** |
| UE 引擎 | `E:\Epic Games\UE_5.7\` |
| 游戏仓库 | `G:\IAOD`（git；`.gitignore` 忽略一切二进制，**生成物绝不放进该仓库**） |
| **显卡** | **待填：`nvidia-smi` 查型号/显存，填到这里 → ________** |

显卡决定量化档位：
- **≥16GB**：官方 bf16/FP8 直跑，速度质量最佳
- **12GB**：INT8 / FP8 量化 + offload
- **8GB**：社区 GGUF 激进量化 + offload，能跑但慢（参考：阿里云开发者社区《MiniMax-H3 8G 显存 AI 漫剧进阶实战》2026-09-29，RTX 20/30/50 系适配）

## 3. 部署方案

### 3.1 目录约定（新建，独立于 IAOD 仓库）

```
G:\vgen\
  ComfyUI\        # ComfyUI 本体 + 它自己独立的 venv（勿与 G:\IAOD\.venv 混用）
  models\         # H3 量化权重（实用子集即可，勿拉全量 498GB 仓库）
  workflows\      # 工作流 JSON（按用途存档 + 记录参数组合）
  prompts\        # 每事件一个 prompt 文件（见 §4.4）
  out\            # 原始生成输出（按批次建子目录；废图留这，不删也行）
  approved\       # ★ 成品交付区：主创筛过的图，文件名保持事件 id
```

### 3.2 安装步骤骨架（细节按显卡档位调整）

1. 装 ComfyUI（git clone 或便携包；**国内网络**：GitHub 慢可用镜像加速，HuggingFace 用 `hf-mirror.com` 或 ModelScope 拉 H3 权重）。
2. 独立 venv，装 torch（CUDA 版）+ ComfyUI 依赖。
3. 拉 **MiniMax-H3 静帧/图像管线**的实用子集：diffusion checkpoint（按显卡选量化版）+ 对应文本编码器（Qwen3-VL 系）+ VAE。**只下工作流清单点名的文件，勿盲下全仓库。**
4. 参考工作流：GitHub `astropuzzo/ComfyUI-MiniMax-H3-Image-Studio`（静帧生成/参考编辑）或 ComfyUI 官方模板库的 H3 模板。
5. **验收装机：** 用 §4.3 的风格锚 prompt 生成 1 张 1216×832 图，能出图、显存不爆、二次生成不重载即通过。
6. 备选路线（H3 图像管线若在本机跑不动）：**Z-Image-Turbo**（6B，Apache-2.0 可商用，16GB 官方线 / 更低走 GGUF；ComfyUI 有官方模板 `Image_z_image_turbo`）。

### 3.3 批量化（装机验收后）

- 工作流存 `workflows\`（含 seed/步数/CFG 全参数），prompt 队列化批量跑（ComfyUI 命令行/API 模式）。
- 每个事件 id 生成 **3 张候选**（不同 seed），出图进 `out\batch_N\<event_id>_s1/s2/s3.png`。

## 4. 生成任务规格（核心交付需求）

### 4.1 分批优先级

| 批 | 内容 | 数量 | 说明 |
|---|---|---|---|
| **P0 样图** | 从 P1 类各抽：`dog_alert` / `false_beacon` / `env_dust_gale` / `comp_porter_fear` / `mirrored_signal` | **5** | 风格校准用，主创过目后再批量 |
| **P1** | 狗 4 + 同伴 4 + 叙事 6（false_beacon/dead_probe/mirrored_signal/half_buried_haul/other_crew_trace/the_quiet） | 14 | 角色与叙事类，价值最高 |
| **P2** | 环境 14（env_* 全部） | 14 | 各星球地貌事件 |
| **P3** | 通用 12（mosquito/friendly_scout/bad_map/rain_break/omen_bird/static_hymn/warm_ration/cracked_seal/beacon_ghost/survey_nod/deep_read/found_track）+ 通用 6（mist_whispers/old_cache/theft_attempt/weight_argue/singing_stones/shared_joke） | 18 | |
| **P4（可选）** | REST 7 + INSANITY 4 + 主线结局关键帧 6 | 17 | 主创拍板要不要 |

**P1–P3 合计 46 张 = 全部世界事件 id：**
`mist_whispers, old_cache, theft_attempt, weight_argue, singing_stones, shared_joke, false_beacon, dead_probe, mirrored_signal, half_buried_haul, other_crew_trace, the_quiet, env_dust_gale, env_ruin_hum, env_ice_crack, env_spore_rain, env_mag_spin, env_salt_glare, env_tide_bell, env_night_pulse, env_echo_wail, env_ash_eruption, env_song_drone, env_glow_tide, env_data_veil, env_ascend_chime, mosquito, friendly_scout, bad_map, rain_break, omen_bird, static_hymn, warm_ration, cracked_seal, beacon_ghost, survey_nod, deep_read, found_track, dog_alert, dog_warmth, dog_steal_ration, dog_steal_ration_solo, comp_scout_boast, comp_porter_fear, comp_mara_translate, comp_shared_watch`

（每条事件的**情境文本**在 `G:\IAOD\ue\IAOD\Content\Script\00_event_data.lua`，按 id 查 `text` 字段——它是画面描述的直接素材：狗在雾里竖毛、断航补给窖、母亲嗓音的频道……画的就是这些瞬间。）

### 4.2 画面规格

- **横版 3:2，1216×832**（或模型最接近的 3:2 尺寸）——UI 顶部横幅裁切与左侧方图裁切两用。
- 构图重心留中偏左（UI 右侧要压文字区）。
- 单主体或单一场景瞬间；**画面里不出现文字**（UI 文字由引擎渲染）。

### 4.3 风格锚（每张 prompt 的固定前缀，不许漂移）

```
retro-futuristic early space age frontier illustration, weathered white paint,
canvas and rivets, muted restrained sci-fi, documentary storybook style,
dusty earth tones with teal and amber accents, subtle film grain,
worn equipment, alien frontier landscape
```

**负面清单（必须进 negative prompt）：**
```
cyberpunk neon, purple glow, pink neon, military HUD, hologram overload,
shiny utopia, text, watermark, logo, anime, photorealistic faces
```

风格依据：`G:\IAOD\briefs\25_ART_MUSIC_DIRECTION.md`（「略脏的早期拓荒、晒白漆、帆布铆钉、克制科幻；禁赛博紫霓虹」）。**风格统一性 > 单张惊艳**——同一套参数只换场景描述词。

### 4.4 命名与交付

- prompt 文件：`prompts\<event_id>.txt`（风格锚 + 该事件的场景描述词）
- 候选输出：`out\batch_N\<event_id>_s1.png` 起
- **成品：主创人工筛选后改名/保持 `<event_id>.png` 放 `approved\`** ——这是给 IAOD 侧的唯一交付物
- 交付即完成：IAOD 侧有现成入库管线（`G:\IAOD\scripts\ue\import_sprint2_assets.py`，改 destination 即用），UI 挂接也由 IAOD 侧做——**本对话不需要碰 G:\IAOD 的任何代码**

## 5. 验收标准

1. 装机验收：§3.2 第 5 步出图通过
2. **风格验收：P0 五张样图并排看像同一套**（主创点头后才准批量）
3. 批量验收：`approved\` 里每张图——文件名=事件 id、3:2、无文字、无负面清单元素、画面与事件情境文本对得上
版权更正（2026-11-01）：H3 与 Music3 使用各自社区许可证，不能视为 Apache-2.0 或无条件商用；MOSS 单独核对 Apache-2.0。以对应版本原始许可证和授权记录为准，详见 STUDIO_OPERATIONS.md。

## 6. 第一步行动清单（新对话开机序列）

1. `nvidia-smi` 查显卡 → 定量化档位（填 §2 待填项）
2. 建 `G:\vgen\` 目录骨架（§3.1）
3. 装 ComfyUI + 独立 venv（国内镜像注意 §3.2 步骤 1）
4. 拉 H3 图像管线实用子集（按档位选量化版）
5. 用 §4.3 风格锚跑通 1 张 → 装机验收
6. 写 P0 五张的 prompt 文件 → 各出 3 候选 → **停在等主创风格验收**
7. 主创过目通过后按 P1→P2→P3 批量；每批完成提醒主创筛图进 `approved\`
8. 全部完成后：在 `G:\vgen\` 里写一份 `DELIVERY.md`（批次清单+参数记录），然后通知主创「图已就绪，可回 IAOD 对话收货入库」

---

*本文档由 IAOD 侧冲刺对话产出（2026-10）。IAOD 侧收货人：`G:\IAOD\AGENTS.md` 指向的当班 agent。*
