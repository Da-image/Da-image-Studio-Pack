#!/usr/bin/env python3
"""
Da-image Studio Pack - SubTools  —  Desktop GUI (dark theme, drag & drop)
Wraps the existing subs.py CLI engine with a modern Tk interface.

Run: python3 subs_gui.py   (requires tkinterdnd2, which is installed in this env)
"""
from __future__ import annotations
import os, sys, threading, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, DND_TEXT
    HAS_DND = True
except ImportError:
    HAS_DND = False

# -------- core engine imports (from subs.py) --------
from subs import (
    parse_srt,
    parse_bilingual_text,
    generate_fcpxml_from_srt_and_txt,
    extract_subtitles_to_txt,
    add_bilingual_subs,
    get_text_from_title,
)

# try to import fcpxml subtitle extract helpers; expose a friendly wrapper
def _extract_subtitle_texts(timeline_path: str) -> list[str]:
    """Return list of subtitle lines (one per caption) from an SRT or FCPXML file.
    Returns texts only, no timing metadata."""
    ext = os.path.splitext(timeline_path)[1].lower()
    texts = []
    if ext == ".srt":
        for e in parse_srt(timeline_path):
            texts.append(e.get("text", "").strip())
    elif ext in (".fcpxml",):
        import xml.etree.ElementTree as ET
        tree = ET.parse(timeline_path)
        for title_el in tree.iter("title"):
            t = get_text_from_title(title_el)
            if t and t.strip():
                texts.append(t.strip())
    return [t for t in texts if t]


# ==============================================================
#  Theme constants  (Dark)
# ==============================================================
APP_NAME = "Da-image Studio Pack - SubTools"
APP_VERSION = "v1.1.6"
APP_CHANGELOG = ("v1.1.6 · 2026-08-04\n"
                 "  · 起始页（未加载时间线）：隐藏右侧功能卡 + 左信息卡 + 底部状态栏，仅显示标题 + 居中的时间线拖拽区\n"
                 "  · 加载时间线后自动切换布局：重新显示左侧信息卡 + 右侧 2 大功能卡 + 底部状态栏\n"
                 "  · 信息卡新增第三块「匹配结果摘要」：校对导出完成后自动显示匹配数/未匹配/匹配率/1:1·merge·combo 比例\n"
                 "  · subs.py generate_fcpxml_from_srt_and_txt 返回值改为 (True, stats)，GUI 用 stats 回填摘要卡\n"
                 "v1.1.5 · 2026-08-04\n"
                 "  · 功能3（回填英文）合并进功能2（校对字幕文案）：\n"
                 "    单语 TXT → 校对模式；双语 TXT → 校对+双语模式（中文 Y=-450、英文 Y=-502，Lane 1/2，\n"
                 "    和原功能3输出结构完全一致），界面简化为 2 大功能\n"
                 "  · 左侧时间线信息卡简化：字幕蓝本信息只有 1 个摘要框（不再分 F2/F3 两栏）\n"
                 "  · 窗口初始尺寸从 1080×720 → 1180×820，最小尺寸 980×640 → 1080×720，避免内容被裁\n"
                 "v1.1.4 · 2026-08-04\n"
                 "  · Feature 2 / 3 TXT 拖拽区放大（320×150 → 340×180）并把「浏览… / 从剪贴板读取」按钮移到\n"
                 "    标题下方，避免 pack_propagate=False 裁剪导致按钮看不到；DZ 本身 DZ 高度也同步放大\n"
                 "  · 左侧时间线信息卡的 TXT 摘要区前加大标题「字幕蓝本信息」\n"
                 "  · 所有「从剪贴板读取」后，左侧和卡片内预览的 TXT 信息摘要同步刷新（已验证与拖拽/浏览一致）\n"
                 "v1.1.3 · 2026-08-04\n"
                 "  · Feature 1 复制成功后，按钮下方新增绿字提示：已复制全部文案+提示词，可粘贴到 DeepSeek / ChatGPT 翻译\n"
                 "  · Feature 2 校对文案增加「从剪贴板读取」按钮（和 Feature 3 一致，支持拖拽 / 浏览 / 剪贴板三种输入）\n"
                 "  · F2 的信息卡/预览/动态导出按钮同步支持「📋 剪贴板」来源（不只有 TXT 文件）\n"
                 "v1.1.2 · 2026-08-04\n"
                 "  · 标题改为「Da-image Studio Pack - SubTools」（中划线 + SubTools 大写）\n"
                 "  · 重置按钮改为蓝色下划线超链接样式「Reset」，去掉左侧灰字说明\n"
                 "  · 时间线信息卡紧凑化：去掉 TXT 区的「功能2/功能3」前缀文字，直接显示摘要\n"
                 "v1.1.1 · 2026-08-04\n"
                 "  · 顶部标题栏新增「重置」按钮：一键清空所有输入回到初始状态\n"
                 "v1.1.0 · 2026-08-04\n"
                 "  · 版本号管理：每次修改递增\n"
                 "  · 时间线信息卡新增 TXT 载入摘要（标准文案 / 英文文案）\n"
                 "  · TXT 拖拽区统一显示浏览按钮，并在载入后显示前 3 行预览 + 字数统计\n"
                 "  · Feature 2 导出按钮动态文案：单语 TXT =「校对」，双语 TXT =「校对+双语」\n"
                 "  · 浅色按钮改用浅灰底+深色字的反色设计；拖拽成功后绿色高亮闪烁\n"
                 "  · 3 大功能统一支持 SRT / FCPXML 双输入\n"
                 "  · Feature 1 剪贴板 / 导出 TXT 尾部附加校对翻译提示词")

BG_APP       = "#1e1e22"
BG_CARD      = "#2a2a30"
BG_CARD_ALT  = "#25252b"
BG_DROP      = "#24242b"
BG_DROP_HOT  = "#2d3a55"
ACCENT       = "#8ab4f8"
ACCENT_HI    = "#a9c6ff"
ACCENT_SOFT  = "#3a4f7a"
BORDER       = "#3a3a42"
FG_PRIMARY   = "#f1f3f4"
FG_SECONDARY = "#9aa0a6"
FG_DISABLED  = "#55575d"
SUCCESS      = "#81c995"
WARN         = "#fbbc04"
ERR          = "#f28b82"
# A light, clearly non-white fg for buttons with a light background (anti-contrast)
LIGHT_BTN_FG = "#202124"
LIGHT_BTN_BG = "#d4d8df"   # true light grey (so it's actually a LIGHT button)

FONT_TITLE    = ("Helvetica", 22, "bold")
FONT_VERSION  = ("Helvetica", 11, "normal")
FONT_CARD_H   = ("Helvetica", 15, "bold")
FONT_BODY     = ("Helvetica", 12, "normal")
FONT_SMALL    = ("Helvetica", 10, "normal")
FONT_DROP     = ("Helvetica", 13, "normal")
FONT_DROP_H1  = ("Helvetica", 16, "bold")
FONT_BTN      = ("Helvetica", 12, "bold")
FONT_STATUS   = ("Helvetica", 11, "normal")


# ==============================================================
#  Timeline ↔ virtual entry helpers (Feature 2/3 input unification)
# ==============================================================
def _timeline_to_virtual_srt(timeline_path: str) -> list[dict]:
    """Convert any accepted timeline input (SRT **or** FCPXML) into the
    same list-of-dicts format that parse_srt() produces, so that the
    proofread pipeline can treat them identically."""
    ext = os.path.splitext(timeline_path)[1].lower()
    if ext == ".srt":
        return parse_srt(timeline_path)
    import xml.etree.ElementTree as ET
    tree = ET.parse(timeline_path)
    out = []
    idx = 1
    def _as_secs(s) -> float:
        if s is None: return 0.0
        s = s.strip()
        if s.endswith("s"): s = s[:-1]
        if "/" in s:
            a, b = s.split("/", 1)
            try: return int(a) / int(b)
            except Exception: return 0.0
        try: return float(s)
        except Exception: return 0.0
    for title_el in tree.iter("title"):
        off = _as_secs(title_el.get("offset"))
        dur = _as_secs(title_el.get("duration"))
        t = get_text_from_title(title_el) or ""
        if t and t.strip():
            out.append({
                "index": idx,
                "start": round(off, 6),
                "end":   round(off + dur, 6),
                "text":  t.strip()
            })
            idx += 1
    return out


def _srt_to_temp_fcpxml(srt_path: str, fps: float = 24) -> str:
    """Convert an SRT timeline into a temporary mono-lingual FCPXML file so
    that the backfill pipeline (add_bilingual_subs) can run on it like a
    native FCPXML.  Returns the temp file path (caller should unlink later)."""
    import tempfile
    tmp = Path(tempfile.gettempdir()) / f"_subtools_srt_as_fcpxml_{os.getpid()}.fcpxml"
    entries = parse_srt(srt_path)
    mono_pairs = [{"orig": e["text"], "trans": ""} for e in entries]
    generate_fcpxml_from_srt_and_txt(entries, mono_pairs, str(tmp), fps=fps,
                                     auto_zero_tc=False, granularity_align=False)
    return str(tmp)


# ==============================================================
#  Helper widgets
# ==============================================================
class DropZone(tk.Frame):
    """A reusable dark drop-zone that accepts files (DND_FILES) and also shows
    a browse-button fallback when DND is not available."""

    def __init__(self, master, accepted_exts=None, placeholder_title="拖拽文件到此处",
                 placeholder_sub="或点击右侧按钮浏览", on_file=None, width=260, height=180,
                 multi=False, accept_text=False, on_text=None):
        super().__init__(master, bg=BG_DROP, highlightthickness=2,
                         highlightbackground=BORDER, highlightcolor=ACCENT,
                         width=width, height=height)
        self.pack_propagate(False)
        self.accepted_exts = tuple(e.lower() for e in (accepted_exts or ()))
        self._on_file_cb = on_file
        self._on_text_cb = on_text
        self._accept_text = accept_text
        self._multi = multi
        self._hover = False

        # content
        inner = tk.Frame(self, bg=BG_DROP)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        self._lbl_title = tk.Label(inner, text=placeholder_title, bg=BG_DROP,
                                   fg=FG_PRIMARY, font=FONT_DROP_H1, justify="center")
        self._lbl_title.pack(anchor="center", pady=(4, 6))

        # action button row (TOP — guaranteed visible even in short dropzones,
        # since it's placed right after title, not pushed to the bottom by expand).
        btn_row = tk.Frame(inner, bg=BG_DROP)
        btn_row.pack(anchor="center", fill="x", pady=(0, 6))
        self._btn = self._make_btn(btn_row, "浏览…", self._on_browse)
        self._btn.pack(side="right")
        if accept_text:
            self._btn_text = self._make_btn(btn_row, "从剪贴板读取", self._on_clipboard)
            self._btn_text.pack(side="right", padx=(0, 8))

        sub = placeholder_sub + (f"\n支持格式：{' / '.join(self.accepted_exts).upper()}" if self.accepted_exts else "")
        self._lbl_sub = tk.Label(inner, text=sub, bg=BG_DROP,
                                 fg=FG_SECONDARY, font=FONT_DROP, justify="center")
        self._lbl_sub.pack(anchor="center", pady=(0, 4))

        # file info label (shown when file is set)
        self._lbl_info = tk.Label(inner, text="", bg=BG_DROP, fg=ACCENT_HI,
                                  font=FONT_SMALL, justify="left", wraplength=width-40)
        self._lbl_info.pack(anchor="w", fill="x")

        # bind DND
        if HAS_DND:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_drop)
                self.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                self.dnd_bind("<<DragLeave>>", self._on_drag_leave)
            except Exception:
                pass

        self._current_file: str | None = None
        self._current_text: str | None = None

    def _make_btn(self, parent, text, cmd):
        btn = tk.Button(parent, text=text, command=cmd,
                        font=FONT_BTN, bd=0, cursor="hand2",
                        bg=LIGHT_BTN_BG, fg=LIGHT_BTN_FG,
                        activebackground=ACCENT_HI, activeforeground=LIGHT_BTN_FG,
                        padx=12, pady=5, highlightthickness=0)
        return btn

    def _set_hover(self, hot: bool):
        self._hover = hot
        bg = BG_DROP_HOT if hot else BG_DROP
        self.configure(bg=bg, highlightbackground=ACCENT if hot else BORDER)
        for w in (self._lbl_title, self._lbl_sub, self._lbl_info,
                  self._lbl_title.master):
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass

    def _on_drag_enter(self, _event=None):
        self._set_hover(True)

    def _on_drag_leave(self, _event=None):
        self._set_hover(False)

    def _validate_paths(self, paths_raw: str) -> list[str]:
        # paths are space-separated; filenames with spaces are enclosed in {}
        out = []
        buf = ""
        in_brace = False
        for ch in paths_raw:
            if ch == "{": in_brace = True; continue
            if ch == "}": in_brace = False; out.append(buf); buf = ""; continue
            if ch == " " and not in_brace:
                if buf: out.append(buf); buf = ""
            else:
                buf += ch
        if buf: out.append(buf)
        return [p for p in out if os.path.exists(p)]

    def _filter_exts(self, paths: list[str]) -> list[str]:
        if not self.accepted_exts: return paths
        return [p for p in paths if p.lower().endswith(self.accepted_exts)]

    def _on_drop(self, event):
        paths = self._validate_paths(event.data)
        ok = self._filter_exts(paths)
        if not ok:
            self._set_info(f"❌ 未识别的文件类型：{paths[0] if paths else '(空)'}", err=True)
            self.after(400, lambda: self._set_hover(False))
            return
        self._set_hover(False)
        if self._multi:
            self._apply_files(ok)
        else:
            self._apply_files([ok[0]])

    def _on_browse(self):
        if self.accepted_exts:
            ftypes = [("Accepted files", " ".join(f"*{e}" for e in self.accepted_exts)),
                      ("All files", "*.*")]
        else:
            ftypes = [("All files", "*.*")]
        if self._multi:
            files = filedialog.askopenfilenames(title="选择文件", filetypes=ftypes)
            if not files: return
            self._apply_files(list(files))
        else:
            f = filedialog.askopenfilename(title="选择文件", filetypes=ftypes)
            if not f: return
            self._apply_files([f])

    def _on_clipboard(self):
        try:
            txt = self.winfo_toplevel().clipboard_get()
        except tk.TclError:
            txt = ""
        if not txt:
            self._set_info("⚠️ 剪贴板为空", err=False)
            return
        self._current_text = txt
        self._current_file = None
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        self._set_info(f"📋 剪贴板：读取到 {len(lines)} 行文字")
        self._flash_success()
        if self._on_text_cb:
            try:
                self._on_text_cb(txt)
            except Exception as e:
                self._set_info(f"❌ 处理失败：{e}", err=True)

    def _apply_files(self, files: list[str]):
        self._current_file = files[0]
        self._current_text = None
        name = os.path.basename(files[0])
        size_kb = os.path.getsize(files[0]) / 1024.0
        self._set_info(f"✅ {name}   ({size_kb:.1f} KB)" +
                       (f"\n共 {len(files)} 个文件" if len(files) > 1 else ""))
        self._flash_success()
        if self._on_file_cb:
            try:
                for f in files:
                    self._on_file_cb(f)
            except Exception as e:
                self._set_info(f"❌ 处理失败：{e}", err=True)

    def _set_info(self, text: str, err: bool = False):
        fg = ERR if err else SUCCESS if "✅" in text else WARN if "⚠️" in text else ACCENT_HI
        self._lbl_info.configure(text=text, fg=fg)

    def _flash_success(self, duration_ms: int = 1400):
        """Give clear visual feedback after a file is dropped successfully: flash
        the outer border SUCCESS-green and temporarily bump the background."""
        orig_bg = self.cget("bg") or BG_DROP
        self.configure(highlightbackground=SUCCESS,
                       highlightthickness=2,
                       bg="#2a3a2f")
        for w in (self._lbl_title, self._lbl_sub, self._lbl_info,
                  self._lbl_title.master):
            try:
                w.configure(bg="#2a3a2f")
            except tk.TclError:
                pass
        def _revert():
            self.configure(highlightbackground=BORDER, highlightthickness=2,
                           bg=BG_DROP)
            for w in (self._lbl_title, self._lbl_sub, self._lbl_info,
                      self._lbl_title.master):
                try:
                    w.configure(bg=BG_DROP)
                except tk.TclError:
                    pass
        self.after(duration_ms, _revert)

    @property
    def current_file(self) -> str | None: return self._current_file
    @property
    def current_text(self) -> str | None: return self._current_text
    def clear(self):
        self._current_file = None
        self._current_text = None
        self._set_info("")

    def set_file(self, path: str, silent=True):
        """Set the drop-zone display to reflect a specific file (without
        re-triggering the on_file callback by default). Useful for mirroring
        state between two drop-zones showing the same file."""
        self._current_file = path
        self._current_text = None
        name = os.path.basename(path)
        try:
            size_kb = os.path.getsize(path) / 1024.0
        except OSError:
            size_kb = 0.0
        self._set_info(f"✅ {name}   ({size_kb:.1f} KB)")
        if not silent and self._on_file_cb:
            try: self._on_file_cb(path)
            except Exception: pass

    def set_text(self, text: str, silent=True):
        """Mirror set_file for clipboard-based text input."""
        self._current_text = text
        self._current_file = None
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        self._set_info(f"📋 剪贴板：读取到 {len(lines)} 行文字")
        if not silent and self._on_text_cb:
            try: self._on_text_cb(text)
            except Exception: pass


class FeatureCard(tk.Frame):
    """A single dark feature card with title + description + enabled/disabled overlay."""

    def __init__(self, master, idx: int, title: str, desc: str,
                 on_build: callable, enabled_getter=None):
        super().__init__(master, bg=BG_CARD, highlightthickness=1,
                         highlightbackground=BORDER, bd=0)
        self._on_build = on_build
        self._enabled_get = enabled_getter or (lambda: True)

        head = tk.Frame(self, bg=BG_CARD)
        head.pack(fill="x", padx=16, pady=(14, 4))

        badge = tk.Label(head, text=f"0{idx}", fg=ACCENT, bg=BG_CARD,
                         font=("SF Pro Display", 20, "bold"))
        badge.pack(side="left")

        title_wrap = tk.Frame(head, bg=BG_CARD)
        title_wrap.pack(side="left", fill="x", expand=True, padx=(12, 0))
        tk.Label(title_wrap, text=title, font=FONT_CARD_H, fg=FG_PRIMARY,
                 bg=BG_CARD, anchor="w").pack(fill="x", anchor="w")
        tk.Label(title_wrap, text=desc, font=FONT_SMALL, fg=FG_SECONDARY,
                 bg=BG_CARD, anchor="w", justify="left", wraplength=520).pack(fill="x", anchor="w", pady=(2, 0))

        self._body_frame = tk.Frame(self, bg=BG_CARD)
        self._body_frame.pack(fill="both", expand=True, padx=16, pady=(10, 14))

    @property
    def body(self) -> tk.Frame: return self._body_frame

    def is_enabled(self) -> bool: return bool(self._enabled_get())


# ==============================================================
#  Main application
# ==============================================================
class SubtoolsApp:
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1280x900")
        self.root.minsize(1180, 800)
        self.root.configure(bg=BG_APP)


        # OS-level theme (ttk)
        try:
            style = ttk.Style(self.root)
            style.theme_use("clam")
        except Exception:
            pass

        # global state
        self._timeline_path: str | None = None
        self._timeline_type: str | None = None   # "srt" | "fcpxml"
        self._timeline_texts: list[str] = []      # pre-loaded caption texts for Feature 1 preview

        self._feature2_txt_path: str | None = None
        self._feature2_txt_content: str | None = None   # clipboard source

        self._build_layout()
        self._rebuild_card_bodies()
        self._refresh_enabled()


    # --------- layout ---------
    def _build_layout(self):
        # header
        header = tk.Frame(self.root, bg=BG_APP, height=78)
        header.pack(fill="x", padx=22, pady=(18, 8))
        header.pack_propagate(False)

        # Left title cluster
        title_wrap = tk.Frame(header, bg=BG_APP)
        title_wrap.pack(side="left", anchor="w")
        tk.Label(title_wrap, text=APP_NAME, font=FONT_TITLE, fg=FG_PRIMARY,
                 bg=BG_APP).pack(side="left", anchor="w")
        tk.Label(title_wrap, text=f"{APP_VERSION}   ·   SRT / FCPXML · 双语字幕工具集",
                 font=FONT_VERSION, fg=FG_SECONDARY, bg=BG_APP
                 ).pack(side="left", padx=(14, 0), pady=(18, 0), anchor="sw")

        # Right-side action buttons
        act_wrap = tk.Frame(header, bg=BG_APP)
        act_wrap.pack(side="right", anchor="e", pady=(26, 0))
        self._btn_reset = tk.Label(
            act_wrap, text="Reset", cursor="hand2",
            font=("Helvetica", 13, "bold underline"),
            fg=ACCENT, bg=BG_APP, activeforeground=ACCENT_HI)
        self._btn_reset.bind("<Button-1>", lambda e: self._reset_all())
        self._btn_reset.bind("<Enter>", lambda e: self._btn_reset.configure(fg=ACCENT_HI))
        self._btn_reset.bind("<Leave>", lambda e: self._btn_reset.configure(fg=ACCENT))
        self._btn_reset.pack(side="right")

        # ==============================================================
        #  LANDING ZONE (shown when NO timeline loaded)
        #     - Timeline DropZone BIG + CENTERED
        #     - No info card, no feature cards, no status bar
        # ==============================================================
        self._landing = tk.Frame(self.root, bg=BG_APP)
        self._landing.pack(fill="both", expand=True, padx=30, pady=10)

        # Vertical spacer (pushes content to vertical center)
        tk.Frame(self._landing, bg=BG_APP, height=60).pack(fill="x")

        landing_title = tk.Label(self._landing,
                                 text="拖拽时间线开始 · Drop your timeline to start",
                                 font=("SF Pro Display", 20, "bold"),
                                 fg=FG_PRIMARY, bg=BG_APP, anchor="center")
        landing_title.pack(pady=(0, 6))
        landing_sub = tk.Label(self._landing,
                               text="支持 SRT（纯字幕时间码）或 FCPXML（Final Cut Pro 工程）两种时间线格式",
                               font=FONT_BODY, fg=FG_SECONDARY, bg=BG_APP, anchor="center")
        landing_sub.pack(pady=(0, 24))

        landing_center = tk.Frame(self._landing, bg=BG_APP, width=560, height=360)
        landing_center.pack()
        landing_center.pack_propagate(False)
        # Big dropzone for landing (width=560)
        self._drop_timeline_landing = DropZone(
            landing_center, accepted_exts=(".srt", ".fcpxml"),
            placeholder_title="拖拽 SRT / FCPXML 到此处",
            placeholder_sub="支持：.srt / .fcpxml\n· 也可点击右上「浏览…」按钮选择文件",
            on_file=self._on_timeline_file,
            width=560, height=340,
        )
        self._drop_timeline_landing.pack(fill="both", expand=True)

        # ==============================================================
        #  WORKSPACE (shown AFTER timeline loaded)
        #     - Left:  small timeline dropzone + info card + match summary
        #     - Right: 2 feature cards
        #     - Bottom: status bar
        # ==============================================================
        self._workspace = tk.Frame(self.root, bg=BG_APP)
        # Do NOT pack() yet — we wait for timeline to load.

        # main split: left (drop+info) + right (features)
        main = tk.Frame(self._workspace, bg=BG_APP)
        main.pack(fill="both", expand=True, padx=22, pady=(2, 10))

        # LEFT: timeline drop zone
        left = tk.Frame(main, bg=BG_APP, width=370)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="主时间线输入", font=FONT_CARD_H, fg=FG_PRIMARY,
                 bg=BG_APP, anchor="w").pack(fill="x", pady=(0, 8))
        tk.Label(left, text="拖拽 SRT 或 FCPXML 到下方，或点击浏览",
                 font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_APP,
                 anchor="w", justify="left").pack(fill="x", pady=(0, 8))

        self._drop_timeline = DropZone(left, accepted_exts=(".srt", ".fcpxml"),
                                       placeholder_title="拖拽 SRT / FCPXML",
                                       placeholder_sub="支持：.srt / .fcpxml",
                                       on_file=self._on_timeline_file,
                                       width=370, height=240)
        self._drop_timeline.pack(fill="x", pady=(2, 14))

        # info card
        self._info_card = tk.Frame(left, bg=BG_CARD, highlightthickness=1,
                                   highlightbackground=BORDER)
        self._info_card.pack(fill="both", expand=True)
        info_inner = tk.Frame(self._info_card, bg=BG_CARD)
        info_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(info_inner, text="时间线信息", font=FONT_CARD_H, fg=FG_PRIMARY,
                 bg=BG_CARD, anchor="w").pack(fill="x")
        tk.Label(info_inner, text="加载主时间线后显示摘要", font=FONT_SMALL,
                 fg=FG_SECONDARY, bg=BG_CARD, anchor="w"
                 ).pack(fill="x", pady=(2, 8))
        self._info_lines = tk.Label(info_inner, text="—", font=FONT_BODY,
                                    fg=FG_SECONDARY, bg=BG_CARD,
                                    anchor="nw", justify="left", wraplength=320)
        self._info_lines.pack(fill="x", anchor="nw")

        # ---- Separator + TXT summary area ----
        tk.Frame(info_inner, bg=BORDER, height=1).pack(fill="x", pady=(10, 6))
        tk.Label(info_inner, text="字幕蓝本信息", font=FONT_CARD_H, fg=FG_PRIMARY,
                 bg=BG_CARD, anchor="w").pack(fill="x", pady=(0, 4))
        self._info_txt = tk.Label(info_inner, text="（未载入）", font=FONT_SMALL,
                                  fg=FG_DISABLED, bg=BG_CARD, anchor="w",
                                  justify="left", wraplength=340)
        self._info_txt.pack(fill="x")

        # ---- Match Result Summary (block 3) ----
        tk.Frame(info_inner, bg=BORDER, height=1).pack(fill="x", pady=(10, 6))
        tk.Label(info_inner, text="匹配结果摘要", font=FONT_CARD_H, fg=FG_PRIMARY,
                 bg=BG_CARD, anchor="w").pack(fill="x", pady=(0, 4))
        self._info_match = tk.Label(info_inner, text="（尚未校对）\n\n校对完成后，此处显示匹配引擎的结果摘要。",
                                    font=FONT_SMALL, fg=FG_DISABLED, bg=BG_CARD, anchor="w",
                                    justify="left", wraplength=340)
        self._info_match.pack(fill="x")

        # RIGHT: feature cards
        right = tk.Frame(main, bg=BG_APP)
        right.pack(side="left", fill="both", expand=True, padx=(20, 0))

        # Top spacer aligns card1 top border with left-side dropzone top border:
        #   left has 2 lines of caption above dropzone + dropzone's own top pady = 52px
        tk.Frame(right, bg=BG_APP, height=52).pack(fill="x")

        self._card1 = FeatureCard(right, 1, "读取时间线字幕",
                                  "提取时间线中所有字幕文本，一键复制到剪贴板或导出到 TXT 文件。\n"
                                  "支持输入：SRT / FCPXML",
                                  on_build=self._build_feat1_body,
                                  enabled_getter=lambda: bool(self._timeline_path))
        self._card1.pack(fill="x", pady=(0, 14))

        self._card2 = FeatureCard(right, 2, "校对 & 双语字幕（生成 FCPXML）",
                                  "以时间线的时间码为骨架（SRT / FCPXML 皆可），用 TXT 的正确文案重新生成最终 FCPXML。\n"
                                  "📘 单语 TXT（每行中文）→ 校对模式，中文校对后导出\n"
                                  "🌐 双语 TXT（中-英每两行一组）→ 校对+双语模式，中文 Y=-450 / 英文 Y=-502 双轨道",
                                  on_build=self._build_feat2_body,
                                  enabled_getter=lambda: bool(self._timeline_path))
        self._card2.pack(fill="x")

        # status bar (part of workspace — hidden on landing)
        self._status = tk.Label(self._workspace, text="就绪", anchor="w",
                                font=FONT_STATUS, bg=BG_APP, fg=FG_SECONDARY,
                                padx=22, pady=8)
        self._status.pack(fill="x", side="bottom")

        # Initial state: show landing, hide workspace + status
        self._workspace.pack_forget()
        if hasattr(self, "_status") and self._status.winfo_ismapped():
            self._status.pack_forget()

    # --------- layout switching helper ---------
    def _switch_to_workspace(self):
        """Hide landing-centered dropzone, show full workspace (left info + right features + status).
        Also mirrors already-input timeline + TXT state into workspace dropzones so the
        user can immediately see the current input state after layout switch."""
        if self._landing.winfo_ismapped():
            self._landing.pack_forget()
        if not self._workspace.winfo_ismapped():
            self._workspace.pack(fill="both", expand=True)
        if hasattr(self, "_status") and not self._status.winfo_ismapped():
            pass
        # --- 1. Timeline DZ (left sidebar): mirror the loaded file ---
        if self._timeline_path:
            for dz in [self._drop_timeline_landing, self._drop_timeline]:
                try: dz.set_file(self._timeline_path)
                except Exception: pass
        # --- 2. Feature 2 TXT DZ: mirror file / clipboard state (in case DZ was
        #        newly rebuilt inside _rebuild_card_bodies after layout switch)
        if getattr(self, "_drop_txt_feat2", None) is not None:
            try:
                if self._feature2_txt_path:
                    self._drop_txt_feat2.set_file(self._feature2_txt_path)
                elif self._feature2_txt_content:
                    self._drop_txt_feat2.set_text(self._feature2_txt_content)
            except Exception:
                pass

    def _switch_to_landing(self):
        """Go back to the empty landing page (after reset). Clear info match summary back to 未校对."""
        if self._workspace.winfo_ismapped():
            self._workspace.pack_forget()
        if not self._landing.winfo_ismapped():
            self._landing.pack(fill="both", expand=True, padx=30, pady=10)
        if hasattr(self, "_info_match"):
            self._info_match.configure(
                text="（尚未校对）\n\n校对完成后，此处显示匹配引擎的结果摘要。",
                fg=FG_DISABLED)


    # --------- global state updates ---------
    def _set_status(self, text: str, kind: str = "info"):
        fg = {"ok": SUCCESS, "warn": WARN, "err": ERR, "info": FG_SECONDARY}.get(kind, FG_SECONDARY)
        self._status.configure(text=text, fg=fg)

    def _reset_all(self):
        """Reset ALL input state (timeline, TXT files, clipboard content, etc.)
        and return the app to exactly the post-launch initial appearance."""
        # 1) Core state vars
        self._timeline_path = None
        self._timeline_type = None
        self._timeline_texts = []
        self._feature2_txt_path = None
        self._feature2_txt_content = None

        # 2) Left info card: reset labels to initial placeholders
        self._info_lines.configure(text="—", fg=FG_SECONDARY)
        self._info_txt.configure(text="（未载入）", fg=FG_DISABLED)

        # 3) Drop zones clear (labels + internal current_file/text)
        for dz in [getattr(self, "_drop_timeline", None),
                   getattr(self, "_drop_timeline_landing", None),
                   getattr(self, "_drop_txt_feat2", None)]:
            if dz is not None:
                try: dz.clear()
                except Exception: pass

        # 4) Rebuild all card bodies from scratch (they read state vars,
        #    so all "请先加载时间线" placeholders will show)
        self._rebuild_card_bodies()

        # 5) Recompute card enable states (all disabled until timeline reloaded)
        self._refresh_enabled()

        # 6) Switch layout BACK to landing page (empty home state)
        self._switch_to_landing()
        # Clear work area status since landing has no status bar
        try: self._status.configure(text="")
        except Exception: pass


    # --------- TXT summary helpers (used by info-card and feature preview) ---------
    @staticmethod
    def _summarize_txt(path: str | None = None, raw_text: str | None = None,
                       max_preview: int = 3) -> dict:
        """Return a summary dict describing a loaded TXT source:
        {lines, total_chars, bilingual, preview_lines[], mode_label, source_name}.
        Works for a file path or raw clipboard text."""
        def _classify(raw: str) -> tuple[bool, int, int, list[str]]:
            nonempty = [ln.strip() for ln in raw.splitlines() if ln and ln.strip()]
            preview = nonempty[:max_preview]
            total_chars = sum(len(l) for l in nonempty)
            # heuristic bilingual detection: sample first N pairs, check if
            # odd lines are mostly latin & even lines are mostly CJK
            try:
                from subs import _is_likely_latin_sentence as _latin
                import itertools as _it
                pairs = list(_it.zip_longest(nonempty[0::2], nonempty[1::2], fillvalue=""))
                pairs = pairs[:20]
                latin_hits = sum(1 for _, even in pairs if even and _latin(even))
                bilingual = (len(pairs) >= 2 and latin_hits / max(1, len(pairs)) >= 0.6)
            except Exception:
                bilingual = False
            return bilingual, len(nonempty), total_chars, preview

        if path and os.path.exists(path):
            try:
                for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
                    try:
                        with open(path, "r", encoding=enc) as f:
                            raw = f.read(); break
                    except UnicodeDecodeError:
                        continue
                else:
                    raw = ""
            except Exception:
                raw = ""
            bilingual, lines, total_chars, preview = _classify(raw)
            return {"source": "file",
                    "source_name": os.path.basename(path),
                    "bilingual": bilingual, "lines": lines,
                    "total_chars": total_chars, "preview_lines": preview}
        elif raw_text is not None:
            bilingual, lines, total_chars, preview = _classify(raw_text)
            return {"source": "clipboard",
                    "source_name": f"剪贴板（{lines} 行）",
                    "bilingual": bilingual, "lines": lines,
                    "total_chars": total_chars, "preview_lines": preview}
        else:
            return {"source": "none", "source_name": "", "bilingual": False,
                    "lines": 0, "total_chars": 0, "preview_lines": []}

    def _render_txt_summary(self, summary: dict) -> str:
        if summary.get("source") == "none" or summary["lines"] == 0:
            return "（未载入）"
        mode_label = "双语（中+英）" if summary["bilingual"] else "单语"
        badge = "📄" if summary["source"] == "file" else "📋"
        head = f"{badge} {summary['source_name']}"
        meta = f"{mode_label} · {summary['lines']} 行 · {summary['total_chars']} 字"
        preview = "  \n".join("  " + (ln[:40] + ("…" if len(ln) > 40 else ""))
                              for ln in summary.get("preview_lines", []))
        return f"{head}\n{meta}" + (f"\n{preview}" if preview else "")

    def _refresh_info_card(self):
        """Re-render the single TXT summary box in the left info card.
        (Feature 3 bilingual track was merged into Feature 2.)"""
        if self._feature2_txt_path:
            s = self._summarize_txt(path=self._feature2_txt_path)
            fg = FG_PRIMARY
        elif self._feature2_txt_content:
            s = self._summarize_txt(raw_text=self._feature2_txt_content)
            fg = FG_PRIMARY
        else:
            s = {"source": "none"}; fg = FG_DISABLED
        self._info_txt.configure(text=self._render_txt_summary(s), fg=fg)



    def _on_timeline_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        texts: list[str] = []
        try:
            texts = _extract_subtitle_texts(path)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("加载失败", f"无法解析该时间线：\n{e}")
            return

        self._timeline_path = path
        self._timeline_type = "srt" if ext == ".srt" else "fcpxml"
        self._timeline_texts = texts

        # info card summary
        base = os.path.basename(path)
        type_text = "SRT 字幕时间线" if ext == ".srt" else "FCPXML 工程时间线"
        dur = ""
        if ext == ".srt":
            try:
                from subs import parse_srt as _p
                ents = _p(path)
                tot_s = ents[-1]["end"] if ents else 0
                dur = f"总长 ≈ {tot_s:,.1f} 秒   "
            except Exception:
                pass
        info = (
            f"📁 文件：{base}\n"
            f"🎬 类型：{type_text}\n"
            f"📝 字幕条数：{len(texts)} 条\n"
            f"⏱️  {dur}\n"
        )
        self._info_lines.configure(text=info, fg=FG_PRIMARY)
        self._set_status(f"已加载时间线：{base}  （{len(texts)} 条字幕）", "ok")

        # Switch layout from landing → workspace (only on first load)
        self._switch_to_workspace()

        # Rebuild each feature body (controls may depend on timeline presence)
        self._rebuild_card_bodies()
        self._refresh_enabled()

        # If the user already loaded TXT *before* timeline (e.g. rebuilt state),
        # re-trigger a pre-match so the match summary is visible right away.
        if self._feature2_txt_path or self._feature2_txt_content:
            self._run_prematch_async()


    def _rebuild_card_bodies(self):
        for card, builder in [(self._card1, self._build_feat1_body),
                              (self._card2, self._build_feat2_body)]:
            for w in card.body.winfo_children():
                w.destroy()
            builder(card.body)


    def _refresh_enabled(self):
        for card in (self._card1, self._card2):
            on = card.is_enabled()
            for w in (card, card.body):
                w.configure(highlightbackground=(ACCENT_SOFT if on else BORDER))
            # enable/disable each child widget
            def _set_state(wid, state):
                try:
                    wid.configure(state=state)
                except tk.TclError:
                    pass
                for ch in wid.winfo_children():
                    _set_state(ch, state)
            _set_state(card.body, "normal" if on else "disable")

    # ==========================================================
    #  Feature 1: Read subtitles → clipboard / export TXT
    # ==========================================================
    def _build_feat1_body(self, body: tk.Frame):
        if not self._timeline_path:
            tk.Label(body, text="⬅️ 请先在左侧加载时间线",
                     font=FONT_BODY, fg=FG_DISABLED, bg=BG_CARD
                     ).pack(anchor="w", pady=(18, 18))
            return

        # preview box (first 10 lines)
        prev_wrap = tk.Frame(body, bg=BG_APP, highlightthickness=1,
                             highlightbackground=BORDER)
        prev_wrap.pack(fill="x", pady=(2, 12))
        tk.Label(prev_wrap, text=f"预览（前 10 / {len(self._timeline_texts)} 条）",
                 font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_APP, anchor="w"
                 ).pack(fill="x", padx=10, pady=(8, 2))
        preview_lines = "\n".join(
            f"  {i+1:>3}.  {ln[:58]}{'…' if len(ln)>58 else ''}"
            for i, ln in enumerate(self._timeline_texts[:10])
        ) if self._timeline_texts else "（空）"
        tk.Label(prev_wrap, text=preview_lines, font=FONT_SMALL,
                 fg=FG_PRIMARY, bg=BG_APP, justify="left", anchor="nw"
                 ).pack(fill="x", padx=10, pady=(2, 10))

        # buttons row
        btns = tk.Frame(body, bg=BG_CARD)
        btns.pack(fill="x", pady=(0, 4))

        # Build the standard "extract" payload exactly matching subs.py's
        # extract_subtitles_to_txt() format: one caption per line, with the
        # GPT "translate & proofread" prompt appended at the very end.
        PROOFREAD_PROMPT = (
            "以上中文修改错别字，并翻译成英文，并严格按照我给的文本分行，"
            "以一行中文一行英文的形式反馈给我，注意不是整段。"
            "再给我一个一键复制的按钮\n"
        )

        def _build_payload() -> str:
            lines = list(self._timeline_texts)
            return "\n".join(lines) + ("\n" if lines else "") + PROOFREAD_PROMPT

        # clipboard button
        def _copy():
            text = _build_payload()
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            self._set_status(
                f"✅ 已复制 {len(self._timeline_texts)} 条字幕 + 翻译提示词 到剪贴板", "ok")
            # Inline green hint under the buttons
            if hasattr(self, "_feat1_copy_hint") and self._feat1_copy_hint.winfo_exists():
                pass
            self._feat1_copy_hint.configure(
                text=("✅ 已复制全部文案和提示词，可粘贴到 DeepSeek、ChatGPT 等对话框中进行翻译"),
                fg=SUCCESS)

        btn_copy = self._primary_btn(btns, "📋 复制全部到剪贴板", _copy)
        btn_copy.pack(side="left", padx=(0, 10))


        def _export_txt():
            default_name = os.path.splitext(os.path.basename(self._timeline_path))[0] + "_captions.txt"
            path = filedialog.asksaveasfilename(
                title="导出为 TXT",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
            if not path: return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(_build_payload())
            except Exception as e:
                messagebox.showerror("导出失败", str(e)); return
            self._set_status(f"✅ 已导出到 {os.path.basename(path)}", "ok")
            messagebox.showinfo("导出完成", f"TXT 已保存到：\n{path}")

        btn_exp = self._secondary_btn(btns, "💾 导出到 TXT", _export_txt)
        btn_exp.pack(side="left")

        # Inline copy-hint label (appears green after user clicks Copy)
        self._feat1_copy_hint = tk.Label(
            body, text="", font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_CARD,
            justify="left", anchor="w", wraplength=620)
        self._feat1_copy_hint.pack(fill="x", pady=(10, 0), anchor="w")

        tk.Label(body, text=f"合计：{len(self._timeline_texts)} 条字幕，"
                            f"{sum(len(t) for t in self._timeline_texts)} 字",
                 font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_CARD, anchor="e"
                 ).pack(fill="x", pady=(10, 0), anchor="e")


    # ==========================================================
    #  Feature 2: Proofread → generate new FCPXML
    # ==========================================================
    def _build_feat2_body(self, body: tk.Frame):
        if not self._timeline_path:
            msg = ("⬅️ 请先在左侧加载时间线（SRT 或 FCPXML 均支持）\n"
                   "• SRT 直接读取原有时间码 & 断句\n"
                   "• FCPXML 会自动提取 title 节点的 offset/duration 作为虚拟 SRT")
            tk.Label(body, text=msg, font=FONT_BODY, fg=FG_DISABLED, bg=BG_CARD,
                     justify="left").pack(anchor="w", pady=(14, 14))
            return

        if self._timeline_type == "srt":
            cap_note = "✅ 当前：SRT 输入 → 直接用逐句时间码做骨架，断句粒度最细"
        else:
            cap_note = "⚠️  当前：FCPXML 输入 → 自动抽取 title 生成虚拟 SRT（每一条 title 对应一个字幕时间槽）"
        tk.Label(body, text=cap_note, font=FONT_SMALL, fg=WARN if self._timeline_type != "srt" else SUCCESS,
                 bg=BG_CARD, anchor="w", justify="left").pack(fill="x", pady=(4, 10))

        # row 1: left = TXT drop, right = FPS + export
        row1 = tk.Frame(body, bg=BG_CARD)
        row1.pack(fill="x", pady=(2, 10))

        # --- TXT drop zone + inline preview under it ---
        dz_frame = tk.Frame(row1, bg=BG_CARD, width=400)
        dz_frame.pack(side="left", fill="both", expand=True)
        dz_frame.pack_propagate(False)
        tk.Label(dz_frame, text="标准文案（TXT / 剪贴板）", font=FONT_BTN, fg=FG_PRIMARY,
                 bg=BG_CARD, anchor="w").pack(fill="x", pady=(0, 6))

        self._drop_txt_feat2 = DropZone(
            dz_frame, accepted_exts=(".txt", ".md"),
            placeholder_title="拖拽 TXT 或从剪贴板读取",
            placeholder_sub="提供校对后的标准文案\n支持 .txt / .md · 右上：浏览\n左上：从剪贴板读取",
            on_file=self._on_feat2_txt,
            on_text=self._on_feat2_text,
            accept_text=True,
            width=400, height=210,
        )
        self._drop_txt_feat2.pack(fill="x")

        # TXT preview (appears after load)
        preview_wrap = tk.Frame(dz_frame, bg=BG_APP, highlightthickness=1,
                                highlightbackground=BORDER)
        preview_wrap.pack(fill="x", pady=(10, 0))
        tk.Label(preview_wrap, text="TXT 预览（前 3 行）",
                 font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_APP, anchor="w"
                 ).pack(fill="x", padx=10, pady=(6, 2))
        self._feat2_preview = tk.Label(preview_wrap, text="（未载入 TXT）",
                                       font=FONT_SMALL, fg=FG_DISABLED, bg=BG_APP,
                                       justify="left", anchor="nw", wraplength=350)
        self._feat2_preview.pack(fill="x", padx=10, pady=(2, 8))

        # --- FPS + Export panel ---
        right = tk.Frame(row1, bg=BG_CARD)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))

        # Top spacer (26px) so the outer highlight-thickness border of opt_frame
        # aligns with the TOP of the left DropZone (offset by the "标准文案…" caption)
        tk.Frame(right, bg=BG_CARD, height=26).pack(fill="x")

        opt_frame = tk.Frame(right, bg=BG_CARD_ALT, highlightthickness=1,
                             highlightbackground=BORDER)
        opt_frame.pack(fill="x", pady=(0, 10))
        opt_inner = tk.Frame(opt_frame, bg=BG_CARD_ALT)
        opt_inner.pack(fill="x", padx=14, pady=12)

        tk.Label(opt_inner, text="时间线帧率", font=FONT_SMALL, fg=FG_SECONDARY,
                 bg=BG_CARD_ALT, anchor="w").grid(row=0, column=0, sticky="w")

        fps_vals = ["23.976", "24", "25", "29.97", "30", "50", "60"]
        self._fps_var = tk.StringVar(value="24")
        fps_cb = ttk.Combobox(opt_inner, textvariable=self._fps_var,
                              values=fps_vals, state="readonly", width=10)
        fps_cb.grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Custom FPS entry
        tk.Label(opt_inner, text="自定义", font=FONT_SMALL, fg=FG_SECONDARY,
                 bg=BG_CARD_ALT, anchor="w").grid(row=0, column=2, sticky="w", padx=(18, 0))
        self._fps_custom = tk.Entry(opt_inner, width=8, bg=BG_APP, fg=FG_PRIMARY,
                                    bd=0, insertbackground=FG_PRIMARY,
                                    highlightthickness=1,
                                    highlightbackground=BORDER)
        self._fps_custom.grid(row=0, column=3, sticky="w", padx=(10, 0))

        # Export button
        def _export():
            if not (self._feature2_txt_path or self._feature2_txt_content):
                messagebox.showwarning("缺少文案", "请先拖拽 TXT，或点击「从剪贴板读取」导入标准文案"); return
            fps = self._read_fps()
            if fps is None: return
            default_base = os.path.splitext(os.path.basename(self._timeline_path))[0] + "_proofread.fcpxml"
            path = filedialog.asksaveasfilename(
                title="导出校对后的 FCPXML",
                defaultextension=".fcpxml", initialfile=default_base,
                filetypes=[("FCPXML", "*.fcpxml"), ("All files", "*.*")])
            if not path: return
            self._run_feat2_export(fps, path)

        self._feat2_export_btn = self._primary_btn(right, "🚀 导出 FCPXML（校对）", _export)
        self._feat2_export_btn.pack(anchor="w", pady=(4, 0))
        tk.Label(right,
                 text="• 时间线（SRT/FCPXML）仅提供时间码 & 粗略断句骨架\n"
                      "• TXT 为标准权威文案；自动修正错别字、对齐粒度\n"
                      "• 单语 TXT 输出单语校对 FCPXML；双语 TXT 自动输出校对+双语",
                 font=FONT_SMALL, fg=FG_SECONDARY, bg=BG_CARD, justify="left",
                 ).pack(fill="x", pady=(10, 2))

        # Sync preview + button caption in case TXT was loaded *before* card rebuild
        self._update_feat2_preview_and_btn()

    def _update_feat2_preview_and_btn(self):
        """Update Feature 2's inline TXT preview and export-button caption based
        on what kind of TXT (bilingual / monolingual) the user loaded."""
        if not getattr(self, "_feat2_preview", None): return
        if not getattr(self, "_feat2_export_btn", None): return
        if self._feature2_txt_path:
            s = self._summarize_txt(path=self._feature2_txt_path)
        elif self._feature2_txt_content:
            s = self._summarize_txt(raw_text=self._feature2_txt_content)
        else:
            self._feat2_preview.configure(text="（未载入 TXT）", fg=FG_DISABLED)
            self._feat2_export_btn.configure(text="🚀 导出 FCPXML（校对）"); return
        mode_label = "双语（中+英）" if s["bilingual"] else "单语"
        badge = "📄" if s["source"] == "file" else "📋"
        previews = "\n".join(
            "  · " + (ln[:50] + ("…" if len(ln) > 50 else ""))
            for ln in s.get("preview_lines", []))
        self._feat2_preview.configure(
            text=f"{badge} {s['source_name']}   {mode_label}\n"
                 f"{s['lines']} 行 · {s['total_chars']} 字\n" +
                 (previews if previews else "（空文本）"),
            fg=FG_PRIMARY)
        # Switch button caption: bilingual = 校对+双语, mono = 校对 only
        if s["bilingual"]:
            self._feat2_export_btn.configure(text="🚀 导出 FCPXML（校对+双语）")
        else:
            self._feat2_export_btn.configure(text="🚀 导出 FCPXML（校对）")


    def _read_fps(self):

        custom = (self._fps_custom.get() or "").strip()
        if custom:
            try: return float(custom)
            except ValueError:
                messagebox.showwarning("帧率无效", f"自定义帧率无效：{custom}"); return None
        try: return float(self._fps_var.get())
        except Exception: return 24

    def _on_feat2_txt(self, path: str):
        self._feature2_txt_path = path
        self._feature2_txt_content = None   # clipboard cleared when user loads a file
        self._set_status(f"📝 标准文案：{os.path.basename(path)}", "ok")
        self._refresh_info_card()
        try: self._update_feat2_preview_and_btn()
        except Exception: pass
        # As soon as TXT is loaded, kick off a pre-match so the info card
        # instantly shows match quality preview (no file written to disk).
        self._run_prematch_async()

    def _on_feat2_text(self, text: str):
        self._feature2_txt_content = text
        self._feature2_txt_path = None      # file cleared when user loads clipboard
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        self._set_status(f"📋 剪贴板：标准文案 {len(lines)} 行已读取", "ok")
        self._refresh_info_card()
        try: self._update_feat2_preview_and_btn()
        except Exception: pass
        # Instant pre-match on clipboard import too
        self._run_prematch_async()


    def _run_feat2_export(self, fps: float, out_path: str):

        self._set_status("⏳ 正在校对 & 生成 FCPXML …（后台运行）", "warn")
        def worker():
            _tmp_clip: Path | None = None
            try:
                from subs import parse_bilingual_text, generate_fcpxml_from_srt_and_txt
                # --- Input unification: SRT / FCPXML → virtual srt_entries[]
                if self._timeline_type == "srt":
                    srt_entries = parse_srt(self._timeline_path)
                else:
                    srt_entries = _timeline_to_virtual_srt(self._timeline_path)
                # --- TXT source: file OR clipboard (write clipboard to temp file)
                import tempfile
                if self._feature2_txt_path:
                    pairs = parse_bilingual_text(self._feature2_txt_path, mode="auto")
                else:
                    _tmp_clip = Path(tempfile.gettempdir()) / "_subtools_f2_clipboard.txt"
                    _tmp_clip.write_text(self._feature2_txt_content or "", encoding="utf-8")
                    pairs = parse_bilingual_text(str(_tmp_clip), mode="auto")
                result = generate_fcpxml_from_srt_and_txt(
                    srt_entries, pairs, out_path, fps=fps,
                    auto_zero_tc=True, granularity_align=True)
                # Backward compat: result may be bool (old subs.py) or (bool, stats) tuple
                ok = result
                stats = None
                if isinstance(result, tuple) and len(result) >= 2:
                    ok, stats = result[0], result[1]
                self.root.after(0, lambda: self._apply_match_summary(stats))
                self.root.after(0, lambda: self._after_export(ok, out_path, "校对完成"))
            except Exception as e:
                traceback.print_exc()
                self.root.after(0, lambda: self._apply_match_summary(None))
                self.root.after(0, lambda: messagebox.showerror("导出失败", str(e)))
                self.root.after(0, lambda: self._set_status(f"❌ 导出失败：{e}", "err"))
            finally:
                if _tmp_clip and _tmp_clip.exists():
                    try: _tmp_clip.unlink()
                    except Exception: pass
        threading.Thread(target=worker, daemon=True).start()

    def _run_prematch_async(self):
        """Run matching WITHOUT writing output file, just to show the user a
        live preview of match stats in the info card, as soon as both
        timeline + TXT are loaded."""
        if not self._timeline_path: return
        if not self._feature2_txt_path and not self._feature2_txt_content: return
        fps = self._read_fps() or 24.0
        self._set_status("⏳ 正在预匹配时间线 & 文案 …（显示匹配结果摘要）", "warn")
        # Show "calculating..." placeholder
        if hasattr(self, "_info_match"):
            self._info_match.configure(
                text="⏳ 正在计算匹配结果 …\n\n（输入变更后会自动刷新）",
                fg=FG_SECONDARY)
        def worker():
            _tmp_clip: Path | None = None
            _tmp_out: Path | None = None
            stats = None
            try:
                import tempfile
                from subs import parse_bilingual_text, generate_fcpxml_from_srt_and_txt
                # srt entries
                parse_srt = None
                from subs import parse_srt
                if self._timeline_type == "srt":
                    srt_entries = parse_srt(self._timeline_path)
                else:
                    srt_entries = _timeline_to_virtual_srt(self._timeline_path)
                # pairs
                if self._feature2_txt_path:
                    pairs = parse_bilingual_text(self._feature2_txt_path, mode="auto")
                else:
                    _tmp_clip = Path(tempfile.gettempdir()) / "_subtools_f2_clipboard.txt"
                    _tmp_clip.write_text(self._feature2_txt_content or "", encoding="utf-8")
                    pairs = parse_bilingual_text(str(_tmp_clip), mode="auto")
                # temp out file (silently discarded)
                _tmp_out = Path(tempfile.gettempdir()) / "_subtools_prematch_tmp.fcpxml"
                result = generate_fcpxml_from_srt_and_txt(
                    srt_entries, pairs, str(_tmp_out), fps=fps,
                    auto_zero_tc=True, granularity_align=True)
                if isinstance(result, tuple) and len(result) >= 2:
                    stats = result[1]
            except Exception as e:
                traceback.print_exc()
                stats = None
                self.root.after(0, lambda: self._set_status(
                    f"⚠️ 预匹配异常：{e}", "warn"))
            finally:
                for p in [_tmp_clip, _tmp_out]:
                    if p and p.exists():
                        try: p.unlink()
                        except Exception: pass
                self.root.after(0, lambda: self._apply_match_summary(stats))
                # update status bar ONLY if there was no error reported above
                if stats is not None:
                    self.root.after(0, lambda: self._set_status(
                        "✅ 匹配完成（显示摘要；点「导出」可写 FCPXML）", "ok"))
        threading.Thread(target=worker, daemon=True).start()


    # ==========================================================
    #  Export completion helpers
    # ==========================================================
    def _apply_match_summary(self, stats: dict | None):
        """Render compact match stats at bottom of info card (Block 3).
        Design: show cover rate at top; two essential lines (results row + algorithm row).
        Keep under 7 lines so user doesn't need to scroll."""
        if not hasattr(self, "_info_match"):
            return
        if not isinstance(stats, dict):
            self._info_match.configure(
                text="（尚未校对）\n\n校对完成后，此处显示匹配引擎的结果摘要。",
                fg=FG_DISABLED)
            return
        n_1to1 = int(stats.get("n_1to1") or 0)
        n_merge = int(stats.get("n_merge_txt") or 0)
        n_combo = int(stats.get("n_combo_srt") or 0)
        out = int(stats.get("output_titles") or 0)
        bi = int(stats.get("matched_bilingual") or 0)
        mono = int(stats.get("matched_orig_only") or 0)
        un = int(stats.get("unmatched") or 0)
        cov = stats.get("coverage_pct")
        cov_str = f"{cov:>5.1f}%" if isinstance(cov, (int, float)) else "N/A"
        total_src = n_1to1 + n_merge + n_combo
        srt_n = int(stats.get("total_srt") or 0)
        total_sec = stats.get("total_sec")
        time_str = ""
        if isinstance(total_sec, (int, float)):
            mins, secs = divmod(int(total_sec), 60)
            hh, mm = divmod(mins, 60)
            time_str = f"{hh:d}:{mm:02d}:{secs:02d}" if hh else f"{mm:02d}:{secs:02d}"
        try:
            cov_val = float(cov)
        except Exception:
            cov_val = 0.0
        if cov_val >= 95.0:
            color = SUCCESS
        elif cov_val >= 80.0:
            color = ACCENT_HI
        elif cov_val >= 60.0:
            color = ACCENT
        else:
            color = WARN

        # Compact version (6–7 lines max): headline + result count + algorithm mix
        r1_bits = []
        if bi:   r1_bits.append(f"双语{bi}")
        if mono: r1_bits.append(f"校对{mono}")
        if un:   r1_bits.append(f"⚠{un}")
        r1 = "  ".join(r1_bits) if r1_bits else "—"

        pct = lambda n: f"{100 * n / total_src:.0f}%" if total_src else "—"
        r2 = (f"1:1 {n_1to1}({pct(n_1to1)})  ·  "
              f"MergeTXT {n_merge}({pct(n_merge)})  ·  "
              f"Combo {n_combo}({pct(n_combo)})")

        lines = [
            f"匹配率 {cov_str}   ·   最终出口 {out} 条",
            "",
            f"📊 结果：{r1}",
            f"🧩 算法：{r2}",
        ]
        if srt_n or time_str:
            parts = []
            if srt_n: parts.append(f"SRT {srt_n}")
            if time_str: parts.append(f"总长 {time_str}")
            lines.append("· " + "   ·   ".join(parts))
        self._info_match.configure(text="\n".join(lines), fg=color)

    def _after_export(self, ok, path: str, title: str):
        if ok:
            self._set_status(f"✅ 导出完成：{os.path.basename(path)}", "ok")
            messagebox.showinfo(title, f"文件已保存：\n{path}")
        else:
            self._set_status("⚠️ 生成未完成，请查看终端日志", "warn")

    # ==========================================================
    #  Buttons
    # ==========================================================
    def _primary_btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd,
                      font=FONT_BTN, bd=0, cursor="hand2",
                      bg=ACCENT, fg=BG_APP, activebackground=ACCENT_HI,
                      activeforeground=BG_APP, padx=18, pady=8,
                      highlightthickness=0)
        return b

    def _secondary_btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd,
                      font=FONT_BTN, bd=0, cursor="hand2",
                      bg=LIGHT_BTN_BG, fg=LIGHT_BTN_FG, activebackground=ACCENT_HI,
                      activeforeground=LIGHT_BTN_FG, padx=18, pady=8,
                      highlightthickness=0)
        return b

    # --------- run ---------
    def run(self):
        self._set_status("就绪 — 拖拽 SRT / FCPXML 到左侧开始")
        self.root.mainloop()


if __name__ == "__main__":
    SubtoolsApp().run()
