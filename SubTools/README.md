# Da-image Studio Pack - SubTools

一个面向字幕校对、双语字幕生成与剪辑时间线处理的桌面工具（macOS / Python / Tk）。

核心围绕 **SRT / FCPXML / TXT** 三类输入输出，目标是：
- 从时间线提取字幕文本
- 用校对后的 TXT 文案自动匹配回时间线
- 生成可回导剪辑软件的 FCPXML（单语校对 / 校对+双语）
- 在 GUI 中给出匹配结果摘要，快速判断质量与覆盖率

---

## 快速开始

### 方式 1：双击启动（推荐）
在目录 `milestone/` 或 `milestone/SubTools/` 下有 `.command` 启动器，双击即可启动 GUI（无需先 cd 到目录）。

- `milestone/SubTools启动.command`
- `milestone/SubTools/SubTools启动.command`

首次使用如果提示无权限，在终端执行一次：
```bash
chmod +x "/Users/da/Documents/trae_projects/DSAprojects/milestone/SubTools启动.command"
chmod +x "/Users/da/Documents/trae_projects/DSAprojects/milestone/SubTools/SubTools启动.command"
```

### 方式 2：命令行启动
```bash
python3 "/Users/da/Documents/trae_projects/DSAprojects/milestone/subs_gui.py"
# 或
python3 "/Users/da/Documents/trae_projects/DSAprojects/milestone/SubTools/subs_gui.py"
```

---

## GUI 工作流

### 第一步：导入主时间线
在起始页拖入：
- `.srt`
- `.fcpxml`

导入后自动切换到工作台，并在时间线拖拽区显示当前文件状态。

### 第二步：导入标准文案 TXT
在功能区导入 TXT：
- 拖拽文件 / 浏览选择
- 或从剪贴板读取

TXT 支持：
- 单语：每行一条
- 双语：中英两行一组（建议严格成对）

### 第三步：查看匹配结果摘要（自动）
当时间线 + TXT 都存在时，GUI 会自动完成预匹配并更新摘要，包括：
- 匹配率 / 最终输出条数
- 双语匹配 / 单语匹配 / 未对齐 fallback
- 1:1 / Merge TXT / Combo SRT 结构占比

**左侧信息卡会同步显示：**
- 🎞  检测帧率：自动读取 FCPXML 的 `<format frameDuration>` 并填入右侧 FPS 框；SRT 无法推导 → 回退 24
- 📁 文件 / 🎬 类型 / 📝 字幕条数 / ⏱ 总长

### 第四步：导出 FCPXML（二选一模式）
Feature 2 校对&双语字幕提供两种导出策略（GUI 默认选中 ②，触发修复后的 v3 算法）：

| 模式（GUI 名称） | 内部引擎 | 适用场景 | 推荐度 |
|---|---|---|---|
| **① 重建 FCPXML**：用时间码 + TXT 标准文案重建 | `generate_fcpxml_from_srt_and_txt()`（Pass0~Pass4 粒度对齐 + Hungarian DP） | 从零新建字幕 / 不需要保留原有调色 / 转场 / 多层素材结构 | ⭐⭐⭐⭐ 字幕重建 |
| **🔴② 更新已有 FCPXML（保留原工程结构）**：直接在原 `<title>` 上替换 + 加英文 | `add_bilingual_subs()` **v3 4 轮 + Hungarian DP 全局最优** | 已有复杂工程（调色/转场/多层）不想丢结构，只想回填英文 + 校对中文 | ⭐⭐⭐⭐⭐ 本次修复目标！ |

#### 模式 ② 的 4 轮全局最优匹配（本次修复的致命错位问题）
**修复前的致命问题（贪心算法）：**
- 老算法从左到右逐条全局 difflib 匹配，只要中间插入 1 条 TXT 没有的中文字幕
- 这条"插入字幕"会一把抢走本该属于后面字幕的 pair，导致后续所有字幕 **全局错位 ±1/N 条**

**修复后的 v3 流程（subs.py L1703-L2148 `add_bilingual_subs`）：**
1. **Pass 1 贪心预对齐**：v2 单调 cursor + 滑窗 ±30，给每条 title 打初匹配
2. **Pass 2 释放低自信**：所有分数 < 0.65 的弱匹配全部丢回未匹配池（防止弱匹配拉偏全局）
3. **Pass 3 滑窗二次对齐**：未匹配 title ↔ 未用 pair ±30 滑窗，非歧义 ≥0.50 才接受
4. **Pass 4 🧩 Hungarian bitmask DP 全局最优（小窗口兜底）**：对剩余有问题的 cluster（≤22 条）建 max-weight 二分图，bitmask DP 求总权重和最大的 1:1 映射，彻底解决"一条弱匹配拉偏全部"

**结果面板（Terminal 结尾）：**
```
🧮 add_bilingual_subs v3 多轮全局最优匹配统计：
  总字幕数（时间线 title）  = 35
  TXT 双语对总数            = 32
  ✅ 命中+加英文           = 32
     · Pass1 强命中(>=0.65)= 27
     · Pass3 滑窗二次命中  = 3
     · 🧩 Pass4 Hungarian全局最优= 2    ← 这条>0就证明贪心错位被DP救回来了
  ⏭  跳过（插入新字幕/txt没）= 3     ← 正好是你插入的3条，被跳过不消费pair
  TXT 已使用率              = 32/32
```

导出后可回导 FCPX / PR / 达芬奇，不会再出现"中间插入字幕 → 后续全错位"。

---

## GUI 新增/更新记录（v1.1.7）
- **默认窗放大**：`1280×900 → 1280×1040` / `minsize 1180×800 → 1180×920`，确保 FPS 框 + 🚀 导出按钮永远在可视区
- **自动读 FPS**：FCPXML 自动解析 `<format frameDuration>` 填到 FPS 下拉框/自定义框；左侧信息卡显示检测值
- **默认导出模式切换**：默认 🔴② 回填（v3 修复引擎），不再默认 ① 重建导致"结果没变化"
- **Feature 2 导出模式二选一选项卡**：每个模式下面直接写清楚它对应的引擎、适用场景，选错不会再误判"没生效"
- **双版本 changelog**：subs_gui.py APP_CHANGELOG 同步 add_bilingual_subs v3 升级说明 + GUI 入口变更

---

## 核心引擎

- `milestone/subs.py`：匹配与导出核心引擎（多层匹配策略；支持单语/双语；回传 stats 供 GUI 渲染摘要）
- `milestone/subs_gui.py`：主 GUI（起始页/工作台双布局、拖拽、后台线程、摘要回填）
- `milestone/SubTools/subs_gui.py`：发布/归档目录中的 GUI 副本（与上同源，支持从父目录定位 subs.py）

---

## 目录结构（节选）

```text
DSAprojects/
└── milestone/
    ├── subs.py
    ├── subs_gui.py
    ├── DaVinciTools/
    └── SubTools/
        ├── subs_gui.py
        ├── SubTools启动.command
        └── README.md
```

---

## 依赖

- Python 3.10+
- tkinter（macOS 通常自带；如果缺失需要安装带 Tk 的 Python）
- tkinterdnd2（用于文件拖拽）

安装示例：
```bash
pip install tkinterdnd2
```

---

## 附：DaVinciTools
`milestone/DaVinciTools/` 下包含达芬奇 Resolve 的辅助脚本（可选），用于补充时间码/素材侧处理，不影响 SubTools 主流程。

---

## License
如需开源发布，请在此补充协议（MIT / Apache-2.0 / All Rights Reserved 等）。