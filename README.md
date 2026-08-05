# Da-image Studio Pack - SubTools

一个面向字幕校对、双语字幕生成与剪辑时间线处理的桌面工具集。

本项目主要围绕 **SRT / FCPXML / TXT** 三类文件工作，核心目标是：

- 从时间线中提取字幕文本
- 用人工校对后的 TXT 文案反向生成新的 FCPXML
- 自动完成单语校对或双语字幕匹配
- 为剪辑流程提供更快、更稳定的字幕处理能力

当前主入口为桌面版 GUI：[subs_gui.py](./subs_gui.py)  
核心匹配引擎为：[subs.py](./subs.py)

---

## 功能概览

### 1. 读取时间线字幕
支持输入：

- `SRT`
- `FCPXML`

可从时间线中提取全部字幕文本，并支持：

- 一键复制到剪贴板
- 导出为 TXT
- 作为后续校对 / 双语生成的时间码骨架

### 2. 校对字幕并生成 FCPXML
以时间线的时间码为基础，读取标准 TXT 文案，重新生成可导入 Final Cut Pro 的 `FCPXML`。

支持两种模式：

- **单语校对模式**
  - TXT 每行一条中文
  - 输出校对后的单语字幕时间线
- **校对 + 双语模式**
  - TXT 按“中英两行一组”组织
  - 输出中英双语字幕轨道

### 3. 匹配结果摘要
导入时间线和 TXT 后，工具会自动进行预匹配，并在界面中显示摘要信息，包括：

- 匹配率
- 最终输出条数
- 双语匹配数
- 单语匹配数
- 未对齐 fallback 数
- 1:1 / Merge TXT / Combo SRT 的占比结构

### 4. 起始页 / 工作台双布局
GUI 采用双阶段布局：

- **起始页**
  - 仅保留标题和居中时间线拖拽区
  - 视觉更干净，聚焦“先导入时间线”
- **工作台**
  - 导入时间线后自动切换
  - 显示信息卡、功能卡、匹配摘要与导出区域

---

## 主要文件

```text
milestone/
├── subs_gui.py              # 桌面 GUI 主程序
├── subs.py                  # 匹配与导出核心引擎
├── README_MATCH48.md        # match48 引擎相关说明
├── stability_gui.py         # 稳定性相关 GUI 工具
├── analyze_stability.py     # 稳定性分析脚本
├── vo2txt.py                # 语音/文本辅助处理脚本
├── DaVinciTools/            # 达芬奇相关辅助工具
└── SubTools/                # GUI 版本归档与说明
```

---

## 技术特点

### 核心匹配引擎
`subs.py` 当前基于 v48 方向的多层匹配策略，支持：

- 本地窗口匹配
- 多轮 fallback
- 单语 / 双语自动识别
- Merge TXT
- Combo SRT
- 匹配统计回传

### GUI
`subs_gui.py` 使用：

- Python
- Tkinter
- tkinterdnd2

特点：

- 原生桌面应用
- 支持拖拽文件
- 黑色主题
- 后台线程导出，避免界面卡死
- 自动同步时间线 / TXT 状态到不同区域

---

## 适用场景

适用于以下工作流：

- 剪辑后从时间线提取字幕文本
- 将 AI / 人工校对后的文案重新对齐回时间线
- 生成可导回 Final Cut Pro 的 FCPXML
- 快速构建单语 / 双语字幕版本
- 对字幕匹配结果进行可视化检查

---

## 运行环境

建议环境：

- macOS
- Python 3.10+
- Final Cut Pro 工作流相关用户
- 可选：DaVinci Resolve 辅助脚本

安装依赖示例：

```bash
pip install tkinterdnd2
```

如果系统 Python 不带 Tk，需要先确认本机支持 `tkinter`。

---

## 启动方式

### 启动 GUI
```bash
cd milestone
python3 subs_gui.py
```

### 启动核心脚本
```bash
cd milestone
python3 subs.py
```

---

## GUI 使用流程

### 第一步：导入主时间线
在起始页拖入以下任一文件：

- `.srt`
- `.fcpxml`

导入后界面会自动切换到工作台。

### 第二步：导入标准文案
在功能 02 区域导入 TXT，可通过：

- 拖拽文件
- 点击浏览
- 从剪贴板读取

TXT 支持：

- 单语：每行一条
- 双语：中英两行一组

### 第三步：查看匹配摘要
导入 TXT 后，界面会自动做一次预匹配，并显示：

- 匹配率
- 匹配结构
- 条目规模
- 未匹配情况

### 第四步：导出 FCPXML
点击导出按钮即可生成：

- 单语校对版 FCPXML
- 或校对 + 双语版 FCPXML

---

## 达芬奇相关工具

目录 [DaVinciTools](./DaVinciTools) 中包含若干 Resolve 辅助脚本，例如：

- 重置素材 Start TC
- 外部运行版 Resolve 脚本

这些工具用于补充字幕和时间线处理链路，但本项目主线仍是 `subs.py + subs_gui.py`。

---

## 项目状态

当前 GUI 版本已迭代到 **v1.1.6**，已完成：

- 起始页极简布局
- 工作台自动切换
- TXT 导入后即时预匹配
- 匹配结果摘要展示
- 功能区排版优化
- 单语 / 双语导出整合

---

## 后续计划

可能继续推进的方向：

- 更完整的异常提示
- 更多时间线格式兼容
- 匹配日志导出
- 批量处理能力
- 更完善的 GitHub 文档与示例素材

---

## 注意事项

- 本工具会基于时间线时间码重建字幕结果，请始终保留原始项目备份
- 双语 TXT 建议保持严格的“中英两行一组”结构
- 不同来源的 FCPXML 可能存在结构差异，建议先做小样本验证
- 导出结果建议先在剪辑软件内人工检查再投入正式项目

---

## License

如需开源发布，可在此补充你的授权协议，例如 MIT / Apache-2.0 / All Rights Reserved。

当前版本可先保留为：

```text
Copyright (c) Da-image Studio
All Rights Reserved
```