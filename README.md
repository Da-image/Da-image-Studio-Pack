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

### 第四步：导出 FCPXML
点击导出即可生成：
- 单语校对版 FCPXML
- 或校对 + 双语版 FCPXML

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