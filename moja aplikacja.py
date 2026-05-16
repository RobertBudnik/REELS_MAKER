import asyncio
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from functools import partial
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    import vlc
except ImportError:
    vlc = None

# ── Sciezki i stale ──────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FOLDERS = {
    "upload":    os.path.join(BASE_DIR, "filmy"),          # gotowe shorty z napisami → upload
    "generated": os.path.join(BASE_DIR, "gotowe_filmy"),   # pliki posrednie
    "published": os.path.join(BASE_DIR, "opublikowane"),
}
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.geometry("1220x760")
        self.minsize(980, 640)
        self.title("Panel Shortow - Robert")

        for folder in FOLDERS.values():
            os.makedirs(folder, exist_ok=True)

        self.vlc_instance = vlc.Instance() if vlc else None
        self.player       = self.vlc_instance.media_player_new() if self.vlc_instance else None
        self.running_process    = None
        self.output_queue       = queue.Queue()
        self.file_frames        = {}
        self.current_video_path = None

        self.grid_columnconfigure(0, weight=0, minsize=430)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(self)
        self.left_panel.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)
        self.left_panel.grid_rowconfigure(2, weight=1)

        self.right_panel = ctk.CTkFrame(self)
        self.right_panel.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=1)

        self.build_action_bar()
        self.build_file_tabs()
        self.build_player()
        self.build_console()

        self.refresh_all_lists()
        self.after(100, self.refresh_console)

    # ── Lewy panel: przyciski akcji ──────────────────────────────────────────

    def build_action_bar(self):
        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Panel pracy",
                     font=("Arial", 20, "bold")).grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(header, text="Gotowy", text_color="gray")
        self.status_label.grid(row=1, column=0, sticky="w")

        actions = ctk.CTkFrame(self.left_panel)
        actions.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)

        # Generuj shorty – odpala main.py (caly pipeline: AI → audio → napisy → filmy/)
        self.btn_generate = ctk.CTkButton(
            actions,
            text="▶  Generuj shorty",
            fg_color="#2ea043", hover_color="#238636",
            font=("Arial", 14, "bold"),
            height=44,
            command=lambda: self.run_script("main.py"),
        )
        self.btn_generate.grid(row=0, column=0, columnspan=2,
                               padx=8, pady=(8, 6), sticky="ew")

        # Upload na YouTube
        self.btn_upload = ctk.CTkButton(
            actions,
            text="⬆  Upload na YouTube",
            fg_color="#1f6feb", hover_color="#1a5fbf",
            height=40,
            command=lambda: self.run_script("youtube_bot_final.py"),
        )
        self.btn_upload.grid(row=1, column=0, columnspan=2,
                             padx=8, pady=(0, 6), sticky="ew")

        # Zatrzymaj / Odswiez
        self.btn_stop_script = ctk.CTkButton(
            actions, text="⏹  Zatrzymaj", state="disabled",
            fg_color="#da3633", hover_color="#b62324", command=self.stop_script,
        )
        self.btn_stop_script.grid(row=2, column=0, padx=(8, 4), pady=(0, 8), sticky="ew")

        self.btn_refresh = ctk.CTkButton(
            actions, text="🔄  Odswiez", command=self.refresh_all_lists,
        )
        self.btn_refresh.grid(row=2, column=1, padx=(4, 8), pady=(0, 8), sticky="ew")

        # Opis pipeline
        ctk.CTkLabel(
            actions,
            text="Pipeline: Gemini AI → TTS + napisy → filmy/ → YouTube",
            text_color="gray",
            font=("Arial", 11),
            wraplength=390,
        ).grid(row=3, column=0, columnspan=2, padx=8, pady=(0, 8))

    # ── Lewy panel: zakladki plikow ──────────────────────────────────────────

    def build_file_tabs(self):
        self.tabview = ctk.CTkTabview(self.left_panel)
        self.tabview.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")

        self.add_file_tab("Do uploadu",   "upload")
        self.add_file_tab("Posrednie",    "generated")
        self.add_file_tab("Opublikowane", "published")

    def add_file_tab(self, label, folder_key):
        tab = self.tabview.add(label)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        toolbar.grid_columnconfigure(0, weight=1)

        count_label = ctk.CTkLabel(toolbar, text="0 plikow", text_color="gray")
        count_label.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            toolbar, text="Otworz folder", width=105,
            command=lambda key=folder_key: self.open_folder(FOLDERS[key]),
        ).grid(row=0, column=1, padx=(8, 0))

        frame = ctk.CTkScrollableFrame(tab, label_text="")
        frame.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        self.file_frames[folder_key] = {"frame": frame, "count": count_label}

    # ── Prawy panel: odtwarzacz ───────────────────────────────────────────────

    def build_player(self):
        player_frame = ctk.CTkFrame(self.right_panel)
        player_frame.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="nsew")
        player_frame.grid_columnconfigure(0, weight=1)
        player_frame.grid_rowconfigure(0, weight=1)

        self.video_screen = ctk.CTkFrame(player_frame, fg_color="black")
        self.video_screen.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        controls = ctk.CTkFrame(player_frame)
        controls.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)

        self.video_title = ctk.CTkLabel(
            controls, text="Brak odtwarzanego pliku", text_color="gray")
        self.video_title.grid(row=0, column=0, columnspan=4,
                              padx=10, pady=(8, 2), sticky="ew")

        self.btn_play = ctk.CTkButton(
            controls, text="Pause", width=80, state="disabled",
            command=self.toggle_play)
        self.btn_play.grid(row=1, column=0, padx=(10, 4), pady=8, sticky="w")

        self.btn_stop_video = ctk.CTkButton(
            controls, text="Stop", width=80, state="disabled",
            fg_color="#da3633", hover_color="#b62324", command=self.stop_video)
        self.btn_stop_video.grid(row=1, column=1, padx=4, pady=8, sticky="w")

        self.btn_open_current = ctk.CTkButton(
            controls, text="Pokaz w folderze", width=125,
            state="disabled", command=self.show_current_in_folder)
        self.btn_open_current.grid(row=1, column=2, padx=4, pady=8, sticky="w")

    # ── Prawy panel: konsola ─────────────────────────────────────────────────

    def build_console(self):
        console = ctk.CTkFrame(self.right_panel)
        console.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        console.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(console, fg_color="transparent")
        header.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Konsola", text_color="gray").grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Wyczysc", width=78,
                      command=self.clear_console).grid(row=0, column=1)

        self.console_box = ctk.CTkTextbox(
            console, height=165, font=("Consolas", 12), wrap="word")
        self.console_box.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
        self.append_console(
            "Gotowy.\n"
            "Kliknij 'Generuj shorty' aby uruchomic pelny pipeline:\n"
            "  Gemini AI (historia) → edge_tts (audio + timings) → napisy → filmy/\n"
            "Potem kliknij 'Upload na YouTube' aby wyslac gotowe filmy.\n"
        )

    # ── Logika skryptow ───────────────────────────────────────────────────────

    def run_script(self, script_name):
        if self.running_process and self.running_process.poll() is None:
            self.append_console("Najpierw zatrzymaj aktualnie uruchomiony skrypt.\n")
            return

        script_path = os.path.join(BASE_DIR, script_name)
        if not os.path.exists(script_path):
            self.append_console(f"Nie znaleziono pliku: {script_path}\n")
            return

        try:
            self.clear_console()
            self.append_console(f"Uruchamiam: {script_name}\n\n")
            self.status_label.configure(text=f"Dziala: {script_name}",
                                        text_color="#2ea043")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            self.running_process = subprocess.Popen(
                [sys.executable, "-u", script_path],
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.set_script_buttons_running(True)
            threading.Thread(
                target=self.read_process_output,
                args=(self.running_process,),
                daemon=True,
            ).start()

        except Exception as error:
            self.append_console(f"Blad uruchamiania: {error}\n")
            self.status_label.configure(text="Blad uruchamiania",
                                        text_color="#da3633")
            self.set_script_buttons_running(False)

    def read_process_output(self, process):
        if process.stdout:
            for line in process.stdout:
                self.output_queue.put(line)
        code = process.wait()
        self.output_queue.put(f"\nSkrypt zakonczony. Kod wyjscia: {code}\n")
        self.output_queue.put("__PROCESS_DONE__")

    def refresh_console(self):
        while not self.output_queue.empty():
            text = self.output_queue.get()
            if text == "__PROCESS_DONE__":
                self.running_process = None
                self.set_script_buttons_running(False)
                self.status_label.configure(text="Gotowy", text_color="gray")
                self.refresh_all_lists()
                continue
            self.append_console(text)
        self.after(100, self.refresh_console)

    def set_script_buttons_running(self, running):
        state = "disabled" if running else "normal"
        self.btn_generate.configure(state=state)
        self.btn_upload.configure(state=state)
        self.btn_stop_script.configure(
            state="normal" if running else "disabled")

    def stop_script(self):
        if self.running_process and self.running_process.poll() is None:
            self.append_console("\nZatrzymuje skrypt...\n")
            self.running_process.terminate()

    def append_console(self, text):
        self.console_box.configure(state="normal")
        self.console_box.insert("end", text)
        self.console_box.see("end")
        self.console_box.configure(state="disabled")

    def clear_console(self):
        self.console_box.configure(state="normal")
        self.console_box.delete("1.0", "end")
        self.console_box.configure(state="disabled")

    # ── Lista plikow ──────────────────────────────────────────────────────────

    def refresh_all_lists(self):
        for key in self.file_frames:
            self.refresh_file_list(key)

    def refresh_file_list(self, folder_key):
        info   = self.file_frames[folder_key]
        frame  = info["frame"]
        folder = FOLDERS[folder_key]

        for widget in frame.winfo_children():
            widget.destroy()

        files = self.get_video_files(folder)
        info["count"].configure(text=f"{len(files)} plikow")

        if not files:
            ctk.CTkLabel(frame, text="Brak filmow.",
                         text_color="gray").grid(row=0, column=0, pady=18)
            return

        for row, path in enumerate(files):
            self.add_file_row(frame, folder_key, path, row)

    def get_video_files(self, folder):
        if not os.path.exists(folder):
            return []
        files = [
            os.path.join(folder, n)
            for n in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, n))
            and n.lower().endswith(VIDEO_EXTENSIONS)
        ]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files

    def add_file_row(self, frame, folder_key, path, row):
        item = ctk.CTkFrame(frame)
        item.grid(row=row, column=0, padx=4, pady=4, sticky="ew")
        item.grid_columnconfigure(0, weight=1)

        name    = os.path.basename(path)
        size_mb = os.path.getsize(path) / (1024 * 1024)
        ctk.CTkLabel(
            item,
            text=f"{name}\n{size_mb:.1f} MB",
            anchor="w", justify="left",
        ).grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        ctk.CTkButton(
            item, text="Play", width=58,
            command=partial(self.play_video, path),
        ).grid(row=0, column=1, padx=(4, 2), pady=8)

        if folder_key == "generated":
            ctk.CTkButton(
                item, text="Do uploadu", width=92,
                command=partial(self.move_to_upload, path),
            ).grid(row=0, column=2, padx=2, pady=8)
        else:
            ctk.CTkButton(
                item, text="Folder", width=65,
                command=partial(self.show_in_folder, path),
            ).grid(row=0, column=2, padx=2, pady=8)

    def move_to_upload(self, path):
        if not os.path.exists(path):
            self.append_console("Plik juz nie istnieje.\n")
            self.refresh_all_lists()
            return
        target = self.unique_target_path(FOLDERS["upload"], os.path.basename(path))
        try:
            shutil.move(path, target)
            self.append_console(f"Przeniesiono: {os.path.basename(target)}\n")
            self.refresh_all_lists()
        except Exception as error:
            self.append_console(f"Blad przenoszenia: {error}\n")

    def unique_target_path(self, folder, filename):
        base, ext = os.path.splitext(filename)
        candidate = os.path.join(folder, filename)
        index = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base}_{index}{ext}")
            index += 1
        return candidate

    # ── Odtwarzacz ────────────────────────────────────────────────────────────

    def play_video(self, path):
        self.current_video_path = path
        if self.player is None:
            self.append_console("Brak VLC. Otwieram domyslnym programem.\n")
            os.startfile(path)
            return
        self.player.stop()
        media = self.vlc_instance.media_new(path)
        self.player.set_media(media)
        if sys.platform.startswith("win"):
            self.player.set_hwnd(self.video_screen.winfo_id())
        self.video_title.configure(text=os.path.basename(path), text_color="white")
        self.btn_play.configure(state="normal", text="Pause")
        self.btn_stop_video.configure(state="normal")
        self.btn_open_current.configure(state="normal")
        self.player.play()

    def toggle_play(self):
        if self.player is None:
            return
        if self.player.is_playing():
            self.player.pause()
            self.btn_play.configure(text="Play")
        else:
            self.player.play()
            self.btn_play.configure(text="Pause")

    def stop_video(self):
        if self.player:
            self.player.stop()
        self.video_title.configure(text="Zatrzymano", text_color="gray")
        self.btn_play.configure(state="disabled", text="Play")
        self.btn_stop_video.configure(state="disabled")

    def show_current_in_folder(self):
        if self.current_video_path:
            self.show_in_folder(self.current_video_path)

    def show_in_folder(self, path):
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            self.open_folder(os.path.dirname(path))

    def open_folder(self, folder):
        os.makedirs(folder, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def destroy(self):
        if self.player:
            self.player.stop()
        if self.running_process and self.running_process.poll() is None:
            self.running_process.terminate()
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
