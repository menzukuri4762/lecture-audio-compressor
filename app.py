import os
import sys
import threading
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import windnd

from compressor import (
    probe_file,
    calculate_optimal_bitrate,
    estimate_output_size_mb,
    AudioCompressor,
    AudioInfo,
    format_duration,
    format_size
)

class FileItem:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.info: AudioInfo = None
        self.status: str = "解析中..."
        self.bitrate_kbps: int = 64
        self.estimated_size_mb: float = 0.0
        self.output_path: str = ""
        self.error_message: str = ""

class LectureAudioCompressorApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("講義音声 AI最適化コンプレッサー - 100MB収縮ツール")
        self.geometry("780x580")
        self.minsize(680, 480)

        # Apply modern color palette
        self.bg_color = "#F1F5F9"
        self.card_bg = "#FFFFFF"
        self.primary_color = "#2563EB"
        self.primary_hover = "#1D4ED8"
        self.text_color = "#0F172A"
        self.subtext_color = "#475569"
        self.border_color = "#CBD5E1"
        self.success_color = "#16A34A"

        self.configure(bg=self.bg_color)

        self.file_items = []
        self.compressor = AudioCompressor()
        self.is_converting = False
        self.cancel_requested = False
        self.last_output_dir = ""

        # Thread queue for UI events
        self.event_queue = queue.Queue()

        self._setup_styles()
        self._build_ui()

        # Bring window to front
        self.lift()
        self.attributes('-topmost', True)
        self.after(500, lambda: self.attributes('-topmost', False))
        self.focus_force()

        # Setup drag and drop after window is ready
        self.after_idle(self._setup_dnd)

        self.after(100, self._process_events)

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Yu Gothic UI", 9))
        style.configure("Card.TFrame", background=self.card_bg, relief="solid", borderwidth=1)
        
        # Treeview styling
        style.configure("Treeview", 
                        background="#FFFFFF", 
                        foreground="#0F172A", 
                        rowheight=28, 
                        fieldbackground="#FFFFFF",
                        font=("Yu Gothic UI", 9))
        style.configure("Treeview.Heading", 
                        background="#E2E8F0", 
                        foreground="#1E293B", 
                        font=("Yu Gothic UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#DBEAFE")], foreground=[("selected", "#1E3A8A")])

        # Progressbar styling
        style.configure("Horizontal.TProgressbar", 
                        background=self.primary_color, 
                        troughcolor="#E2E8F0", 
                        borderwidth=0, 
                        thickness=14)

    def _build_ui(self):
        # Main container with padding
        main_frame = tk.Frame(self, bg=self.bg_color, padx=14, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Header (TOP)
        header_frame = tk.Frame(main_frame, bg=self.bg_color)
        header_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        title_lbl = tk.Label(
            header_frame,
            text="講義音声 AI最適化コンプレッサー",
            font=("Yu Gothic UI", 14, "bold"),
            bg=self.bg_color,
            fg="#1E293B"
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame,
            text="90分前後の講義録音を、AI文字起こし向けに100MB未満のMP3に圧縮・最適化します",
            font=("Yu Gothic UI", 8),
            bg=self.bg_color,
            fg=self.subtext_color
        )
        subtitle_lbl.pack(anchor="w")

        # 2. Bottom Controls (BOTTOM - 先にpackすることで画面外への見切れを100%防止)
        bottom_frame = tk.Frame(main_frame, bg=self.bg_color)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        self.progress_bar = ttk.Progressbar(bottom_frame, orient="horizontal", mode="determinate", style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X, pady=(0, 3))

        status_bar = tk.Frame(bottom_frame, bg=self.bg_color)
        status_bar.pack(fill=tk.X, pady=(0, 6))

        self.lbl_status = tk.Label(status_bar, text="準備完了（音声ファイルをドロップしてください）", font=("Yu Gothic UI", 9), bg=self.bg_color, fg="#334155")
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_eta = tk.Label(status_bar, text="", font=("Yu Gothic UI", 9), bg=self.bg_color, fg=self.subtext_color)
        self.lbl_eta.pack(side=tk.RIGHT)

        btn_bar = tk.Frame(bottom_frame, bg=self.bg_color)
        btn_bar.pack(fill=tk.X)

        self.btn_open_folder = tk.Button(
            btn_bar,
            text="📁 保存先を開く",
            command=self._open_output_folder,
            bg="#FFFFFF",
            fg="#334155",
            font=("Yu Gothic UI", 9),
            padx=10,
            pady=4,
            relief="groove",
            state="disabled"
        )
        self.btn_open_folder.pack(side=tk.LEFT)

        self.btn_cancel = tk.Button(
            btn_bar,
            text="中止",
            command=self._cancel_conversion,
            bg="#FEE2E2",
            fg="#991B1B",
            font=("Yu Gothic UI", 9),
            padx=12,
            pady=4,
            relief="groove",
            state="disabled"
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_start = tk.Button(
            btn_bar,
            text="⚡ 100MB以下に変換開始",
            command=self._start_conversion,
            bg=self.primary_color,
            fg="#FFFFFF",
            activebackground=self.primary_hover,
            activeforeground="#FFFFFF",
            font=("Yu Gothic UI", 10, "bold"),
            padx=16,
            pady=5,
            relief="flat",
            cursor="hand2"
        )
        self.btn_start.pack(side=tk.RIGHT)

        # 3. Drop Zone (TOP)
        self.drop_frame = tk.Frame(
            main_frame,
            bg="#F8FAFC",
            highlightbackground="#94A3B8",
            highlightcolor=self.primary_color,
            highlightthickness=2,
            padx=12,
            pady=8,
            cursor="hand2"
        )
        self.drop_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        self.drop_frame.bind("<Button-1>", lambda e: self._choose_files())

        drop_inner = tk.Frame(self.drop_frame, bg="#F8FAFC")
        drop_inner.pack()
        drop_inner.bind("<Button-1>", lambda e: self._choose_files())

        drop_icon_lbl = tk.Label(drop_inner, text="📂", font=("Segoe UI Emoji", 14), bg="#F8FAFC")
        drop_icon_lbl.pack(side=tk.LEFT, padx=(0, 6))
        drop_icon_lbl.bind("<Button-1>", lambda e: self._choose_files())

        self.drop_lbl = tk.Label(
            drop_inner,
            text="ここに講義音声・動画ファイルをドラッグ＆ドロップ（またはクリックして選択）",
            font=("Yu Gothic UI", 10, "bold"),
            bg="#F8FAFC",
            fg="#1E293B"
        )
        self.drop_lbl.pack(side=tk.LEFT)
        self.drop_lbl.bind("<Button-1>", lambda e: self._choose_files())

        # 4. Settings Card (TOP - コンパクトな2行設計)
        settings_card = tk.LabelFrame(
            main_frame,
            text=" 変換設定 ",
            font=("Yu Gothic UI", 8, "bold"),
            bg=self.card_bg,
            fg="#1E293B",
            padx=8,
            pady=4,
            relief="solid",
            borderwidth=1
        )
        settings_card.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))

        # Row 1: Target size + Mode
        row1 = tk.Frame(settings_card, bg=self.card_bg)
        row1.pack(fill=tk.X, pady=1)

        tk.Label(row1, text="目標サイズ:", font=("Yu Gothic UI", 8, "bold"), bg=self.card_bg, fg="#334155").pack(side=tk.LEFT)
        self.var_target_size = tk.StringVar(value="95")
        for val, label in [("95", "95MB (100MB未満)"), ("25", "25MB (Whisper)"), ("50", "50MB")]:
            tk.Radiobutton(row1, text=label, variable=self.var_target_size, value=val, bg=self.card_bg, fg="#1E293B", font=("Yu Gothic UI", 8), command=self._recalculate_all).pack(side=tk.LEFT, padx=3)

        tk.Label(row1, text=" | モード:", font=("Yu Gothic UI", 8, "bold"), bg=self.card_bg, fg="#334155").pack(side=tk.LEFT, padx=(6, 2))
        self.var_mode = tk.StringVar(value="ai_voice")
        for val, label in [("ai_voice", "🎙️ AI最適化 (推奨)"), ("fit_target", "🎯 目標上限フィット"), ("compact", "🪶 軽量")]:
            tk.Radiobutton(row1, text=label, variable=self.var_mode, value=val, bg=self.card_bg, fg="#1E293B", font=("Yu Gothic UI", 8), command=self._recalculate_all).pack(side=tk.LEFT, padx=3)

        # Row 2: Optimization checkbox + Output folder
        row2 = tk.Frame(settings_card, bg=self.card_bg)
        row2.pack(fill=tk.X, pady=1)

        self.var_ai_optimize = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row2,
            text="AI音声強調 (空調ノイズ低減 ＋ 小声均一化 ＋ モノラル化)",
            variable=self.var_ai_optimize,
            bg=self.card_bg,
            fg="#0F172A",
            font=("Yu Gothic UI", 8, "bold")
        ).pack(side=tk.LEFT)

        tk.Label(row2, text=" | 保存先:", font=("Yu Gothic UI", 8, "bold"), bg=self.card_bg, fg="#334155").pack(side=tk.LEFT, padx=(6, 2))
        self.var_out_same = tk.BooleanVar(value=True)
        tk.Radiobutton(row2, text="元と同じフォルダ", variable=self.var_out_same, value=True, bg=self.card_bg, fg="#1E293B", font=("Yu Gothic UI", 8), command=self._toggle_out_dir).pack(side=tk.LEFT)
        tk.Radiobutton(row2, text="指定先:", variable=self.var_out_same, value=False, bg=self.card_bg, fg="#1E293B", font=("Yu Gothic UI", 8), command=self._toggle_out_dir).pack(side=tk.LEFT)

        self.var_custom_path = tk.StringVar(value="")
        self.entry_custom_dir = tk.Entry(row2, textvariable=self.var_custom_path, state="disabled", width=16, font=("Yu Gothic UI", 8))
        self.entry_custom_dir.pack(side=tk.LEFT, padx=2)

        self.btn_browse_dir = tk.Button(row2, text="参照", state="disabled", command=self._browse_custom_dir, bg="#F1F5F9", font=("Yu Gothic UI", 8), relief="groove")
        self.btn_browse_dir.pack(side=tk.LEFT, padx=2)

        # 5. File List (Remaining space, expand=True)
        list_container = tk.Frame(main_frame, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1)
        list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # List Toolbar
        list_bar = tk.Frame(list_container, bg="#F8FAFC", padx=6, pady=4)
        list_bar.pack(fill=tk.X)

        list_title = tk.Label(list_bar, text="変換対象ファイル一覧", font=("Yu Gothic UI", 9, "bold"), bg="#F8FAFC", fg="#334155")
        list_title.pack(side=tk.LEFT)

        # 上部ツールバーにも「⚡ 変換開始」ボタンを配置（ダブル配置でどこからでも押せる）
        self.btn_start_top = tk.Button(
            list_bar,
            text="⚡ 変換開始",
            command=self._start_conversion,
            bg=self.primary_color,
            fg="#FFFFFF",
            font=("Yu Gothic UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=2,
            cursor="hand2"
        )
        self.btn_start_top.pack(side=tk.RIGHT, padx=4)

        btn_mobile = tk.Button(list_bar, text="📱 スマホ版", command=self._open_mobile_server, bg="#F0FDF4", fg="#166534", relief="groove", font=("Yu Gothic UI", 8, "bold"))
        btn_mobile.pack(side=tk.RIGHT, padx=4)

        btn_add = tk.Button(list_bar, text="＋ ファイル追加", command=self._choose_files, bg="#FFFFFF", fg="#334155", relief="groove", font=("Yu Gothic UI", 8))
        btn_add.pack(side=tk.RIGHT, padx=4)

        btn_clear = tk.Button(list_bar, text="クリア", command=self._clear_files, bg="#FFFFFF", fg="#DC2626", relief="groove", font=("Yu Gothic UI", 8))
        btn_clear.pack(side=tk.RIGHT, padx=4)

        # Treeview with Scrollbar
        tree_frame = tk.Frame(list_container, bg="#FFFFFF")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "duration", "original_size", "bitrate", "est_size", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="ファイル名")
        self.tree.heading("duration", text="再生時間")
        self.tree.heading("original_size", text="元サイズ")
        self.tree.heading("bitrate", text="適用ビットレート")
        self.tree.heading("est_size", text="変換後サイズ(推定)")
        self.tree.heading("status", text="ステータス")

        self.tree.column("name", width=240, anchor="w")
        self.tree.column("duration", width=75, anchor="center")
        self.tree.column("original_size", width=80, anchor="center")
        self.tree.column("bitrate", width=95, anchor="center")
        self.tree.column("est_size", width=120, anchor="center")
        self.tree.column("status", width=110, anchor="center")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _setup_dnd(self):
        try:
            windnd.hook_dropfiles(self, self._on_drop_files)
        except Exception as e:
            print("windnd hook error:", e)

    def _on_drop_files(self, files):
        file_paths = []
        for f in files:
            try:
                p = f.decode("utf-8") if isinstance(f, bytes) else str(f)
                file_paths.append(p)
            except UnicodeDecodeError:
                p = f.decode("cp932", errors="ignore")
                file_paths.append(p)
        self._add_files(file_paths)

    def _choose_files(self):
        paths = filedialog.askopenfilenames(
            title="音声・動画ファイルを選択",
            filetypes=[
                ("講義音声・動画ファイル", "*.m4a *.mp3 *.wav *.aac *.flac *.wma *.ogg *.mp4 *.mkv *.webm *.mov *.avi"),
                ("すべてのファイル", "*.*")
            ]
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, file_paths):
        new_items = []
        for path in file_paths:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                continue
            # avoid duplicates
            if any(item.filepath == path for item in self.file_items):
                continue
            item = FileItem(path)
            self.file_items.append(item)
            new_items.append(item)

        if not new_items:
            return

        # Start probing in background thread
        threading.Thread(target=self._probe_items_worker, args=(new_items,), daemon=True).start()

    def _probe_items_worker(self, items):
        for item in items:
            try:
                info = probe_file(item.filepath)
                item.info = info
                if not info.has_audio:
                    item.status = "音声なし"
                else:
                    item.status = "待機中"
                    self._update_item_bitrate_and_est(item)
            except Exception as e:
                item.status = "エラー"
                item.error_message = str(e)

            self.event_queue.put(("update_table", None))

    def _update_item_bitrate_and_est(self, item: FileItem):
        if not item.info or not item.info.has_audio:
            return

        target_mb = float(self.var_target_size.get())
        mode = self.var_mode.get()

        kbps = calculate_optimal_bitrate(item.info.duration, target_mb=target_mb, mode=mode)
        item.bitrate_kbps = kbps
        item.estimated_size_mb = estimate_output_size_mb(item.info.duration, kbps)

    def _recalculate_all(self):
        for item in self.file_items:
            if item.status in ("待機中", "解析中..."):
                self._update_item_bitrate_and_est(item)
        self._refresh_table()

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for idx, item in enumerate(self.file_items):
            dur_str = format_duration(item.info.duration) if item.info else "-"
            orig_size = format_size(item.info.file_size) if item.info else "-"
            br_str = f"{item.bitrate_kbps} kbps" if item.info and item.info.has_audio else "-"
            est_str = f"約 {item.estimated_size_mb:.1f} MB" if item.info and item.info.has_audio else "-"
            
            # visual cue if estimated size is safely within 100MB
            if item.info and item.estimated_size_mb <= float(self.var_target_size.get()):
                est_str += " (OK)"

            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(item.filename, dur_str, orig_size, br_str, est_str, item.status)
            )

    def _clear_files(self):
        if self.is_converting:
            messagebox.showwarning("変換中", "変換実行中はリストをクリアできません。")
            return
        self.file_items.clear()
        self._refresh_table()
        self.lbl_status.config(text="ファイルをクリアしました")

    def _toggle_out_dir(self):
        if self.var_out_same.get():
            self.entry_custom_dir.config(state="disabled")
            self.btn_browse_dir.config(state="disabled")
        else:
            self.entry_custom_dir.config(state="normal")
            self.btn_browse_dir.config(state="normal")

    def _browse_custom_dir(self):
        d = filedialog.askdirectory(title="保存先フォルダを選択")
        if d:
            self.var_custom_path.set(d)

    def _open_output_folder(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            if sys.platform == "win32":
                os.startfile(self.last_output_dir)
            else:
                subprocess.Popen(["xdg-open", self.last_output_dir])

    def _open_mobile_server(self):
        # Launch web/server.py in background and notify user
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "server.py")
        subprocess.Popen([sys.executable, script_path])
        messagebox.showinfo(
            "📱 スマホ版Webアプリ",
            "スマホ用Webサーバーを起動しました。\nブラウザが開き、同一Wi-Fi内のスマホからアクセスできるURLが表示されます。\n\nスマホのSafariやChromeで開くと、PCなしで直接スマホ内で音声を100MB以下に圧縮できます！"
        )

    def _start_conversion(self):
        if self.is_converting:
            return

        valid_items = [it for it in self.file_items if it.info and it.info.has_audio and it.status != "完了"]
        if not valid_items:
            messagebox.showinfo("変換対象なし", "変換可能な音声ファイルがリストにありません。\nファイルをドラッグ＆ドロップしてください。")
            return

        if not self.var_out_same.get():
            out_d = self.var_custom_path.get().strip()
            if not out_d or not os.path.isdir(out_d):
                messagebox.showerror("保存先エラー", "有効な保存先フォルダを指定してください。")
                return

        self.is_converting = True
        self.cancel_requested = False
        self.btn_start.config(state="disabled")
        self.btn_start_top.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.btn_open_folder.config(state="disabled")

        threading.Thread(target=self._convert_worker, args=(valid_items,), daemon=True).start()

    def _cancel_conversion(self):
        if self.is_converting:
            self.cancel_requested = True
            self.lbl_status.config(text="中止処理中...")
            self.compressor.cancel()

    def _convert_worker(self, items):
        total_items = len(items)
        success_count = 0
        ai_opt = self.var_ai_optimize.get()

        for idx, item in enumerate(items):
            if self.cancel_requested:
                item.status = "中止"
                break

            item.status = "変換中..."
            self.event_queue.put(("update_table", None))

            # Determine output filepath
            base_name, _ = os.path.splitext(item.filename)
            out_name = f"{base_name}_compressed.mp3"

            if self.var_out_same.get():
                out_dir = os.path.dirname(item.filepath)
            else:
                out_dir = self.var_custom_path.get().strip()

            out_path = os.path.join(out_dir, out_name)
            item.output_path = out_path
            self.last_output_dir = out_dir

            def progress_cb(pct, status_text):
                overall_pct = ((idx + (pct / 100.0)) / total_items) * 100.0
                self.event_queue.put(("progress", (overall_pct, f"[{idx+1}/{total_items}] {item.filename}: {status_text}")))

            try:
                ok = self.compressor.convert(
                    input_path=item.filepath,
                    output_path=out_path,
                    duration_sec=item.info.duration,
                    bitrate_kbps=item.bitrate_kbps,
                    ai_optimize=ai_opt,
                    progress_callback=progress_cb
                )

                if ok:
                    actual_size = os.path.getsize(out_path)
                    item.status = f"完了 ({format_size(actual_size)})"
                    success_count += 1
                else:
                    item.status = "中止"
            except Exception as e:
                item.status = "失敗"
                item.error_message = str(e)

            self.event_queue.put(("update_table", None))

        self.event_queue.put(("finished", (success_count, total_items)))

    def _process_events(self):
        try:
            while not self.event_queue.empty():
                evt_type, data = self.event_queue.get_nowait()
                if evt_type == "update_table":
                    self._refresh_table()
                elif evt_type == "progress":
                    overall_pct, text = data
                    self.progress_bar["value"] = overall_pct
                    self.lbl_status.config(text=text)
                elif evt_type == "finished":
                    success_count, total_items = data
                    self.is_converting = False
                    self.btn_start.config(state="normal")
                    self.btn_start_top.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    self.btn_open_folder.config(state="normal")
                    self.progress_bar["value"] = 100.0 if success_count == total_items else 0.0

                    if self.cancel_requested:
                        self.lbl_status.config(text="変換が中止されました")
                        messagebox.showinfo("中止", "変換を中止しました。")
                    elif success_count == total_items:
                        self.lbl_status.config(text=f"全処理完了 ({success_count}/{total_items} 件変換成功)")
                        try:
                            import winsound
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                        except Exception:
                            pass
                        messagebox.showinfo("変換完了", f"{success_count} 件の講義音声を 100MB 未満のMP3へ変換しました！\n\n保存先: {self.last_output_dir}")
                    else:
                        errors = [f"・{it.filename}: {it.error_message}" for it in self.file_items if it.status == "失敗"]
                        err_text = "\n".join(errors[:3])
                        self.lbl_status.config(text=f"一部失敗 ({success_count}/{total_items} 件成功)")
                        messagebox.showerror("変換エラー", f"変換中にエラーが発生しました:\n\n{err_text}")
        finally:
            self.after(100, self._process_events)

if __name__ == "__main__":
    app = LectureAudioCompressorApp()
    app.mainloop()
