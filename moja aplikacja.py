import customtkinter as ctk
from functools import partial
import os
import subprocess
import sys

try:
    import vlc
except ImportError:
    print("❌ Błąd: Nie znaleziono biblioteki 'vlc'. Zainstaluj ją wpisując w terminalu: pip install python-vlc")
    vlc = None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("1000x700")
        self.title("Zarządca Filmów - Robert")

        self.vlc_instance = vlc.Instance() if vlc else None
        self.player = self.vlc_instance.media_player_new() if self.vlc_instance else None

        self.grid_columnconfigure(0, weight=1)  
        self.grid_columnconfigure(1, weight=2) 
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="nsew")

        self.tabview.add("main.py")
        self.tabview.add("subtitles.py")
        self.tabview.add("youtube_bot_final.py")

        self.lista_frame1 = self.zbuduj_zakladke(
            "main.py",
            r"C:\Users\Robert\PycharmProjects\PythonProject2\gotowe_filmy"
        )
        self.lista_frame2 = self.zbuduj_zakladke(
            "subtitles.py",
            r"C:\Users\Robert\PycharmProjects\PythonProject2\filmy"
        )
        self.lista_frame3 = self.zbuduj_zakladke(
            "youtube_bot_final.py",
            r"C:\Users\Robert\PycharmProjects\PythonProject2\opublikowane"
        )

        self.player_frame = ctk.CTkFrame(self)
        self.player_frame.grid(row=0, column=1, padx=(10, 20), pady=20, sticky="nsew")
        self.player_frame.grid_rowconfigure(0, weight=1)
        self.player_frame.grid_columnconfigure(0, weight=1)

        self.video_screen = ctk.CTkFrame(self.player_frame, fg_color="black")
        self.video_screen.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsew")

        self.controls_frame = ctk.CTkFrame(self.player_frame, height=50)
        self.controls_frame.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        self.lbl_tytul = ctk.CTkLabel(self.controls_frame, text="Brak odtwarzanego pliku", text_color="gray")
        self.lbl_tytul.pack(side="top", pady=(5, 0))

        # Przyciski sterujące
        self.btn_play = ctk.CTkButton(self.controls_frame, text="⏸ Pause", width=80, state="disabled",
                                      command=self.toggle_play)
        self.btn_play.pack(side="left", padx=10, pady=10)

        self.btn_stop = ctk.CTkButton(self.controls_frame, text="⏹ Stop", width=80, state="disabled",
                                      fg_color="#dc3545", hover_color="#c82333", command=self.stop_video)
        self.btn_stop.pack(side="left", padx=10, pady=10)

    def zbuduj_zakladke(self, nazwa_zakladki, sciezka_do_folderu):
        """Funkcja pomocnicza budująca zawartość danej zakładki (przyciski i listę)"""
        tab = self.tabview.tab(nazwa_zakladki)

        btn_run = ctk.CTkButton(
            tab, text=f"▶ URUCHOM {nazwa_zakladki}", fg_color="#28a745", hover_color="#218838",
            command=lambda: self.uruchom_skrypt(nazwa_zakladki)
        )
        btn_run.pack(pady=(10, 5), fill="x", padx=10)

        lista_frame = ctk.CTkScrollableFrame(tab, label_text="Twoje Filmy")

        btn_refresh = ctk.CTkButton(
            tab, text="📁 Odśwież listę",
            command=lambda: self.wczytaj_i_pokaz(sciezka_do_folderu, lista_frame)
        )
        btn_refresh.pack(pady=(5, 10), fill="x", padx=10)

        lista_frame.pack(pady=5, padx=10, fill="both", expand=True)
        return lista_frame

    def uruchom_skrypt(self, nazwa_skryptu):
        print(f"Uruchamiam skrypt: {nazwa_skryptu}...")
        folder_projektu = r"C:\Users\Robert\PycharmProjects\PythonProject2"
        pelna_sciezka = os.path.join(folder_projektu, nazwa_skryptu)

        if not os.path.exists(pelna_sciezka):
            print(f"❌ Błąd: Nie znaleziono pliku {pelna_sciezka}")
            return

        try:
            if os.name == 'nt':
                subprocess.Popen([sys.executable, pelna_sciezka], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen([sys.executable, pelna_sciezka])
        except Exception as e:
            print(f"❌ Wystąpił błąd podczas uruchamiania {nazwa_skryptu}: {e}")

    def wczytaj_i_pokaz(self, sciezka, frame):
        if not os.path.exists(sciezka):
            print(f"Folder nie istnieje: {sciezka}")
            # Czyścimy starą listę
            for widget in frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(frame, text="Folder nie istnieje!").pack(pady=20)
            return

        for widget in frame.winfo_children():
            widget.destroy()

        pliki = os.listdir(sciezka)
        filmy = [f for f in pliki if f.endswith((".mp4", ".mkv", ".avi"))]

        if not filmy:
            ctk.CTkLabel(frame, text="Brak filmów.").pack(pady=20)
            return

        for film in filmy:
            pelna_sciezka = os.path.join(sciezka, film)
            btn = ctk.CTkButton(
                frame,
                text=f"🎬 {film}",
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("#dbdbdb", "#2b2b2b"),
                command=partial(self.odtworz_film_w_aplikacji, pelna_sciezka)
            )
            btn.pack(fill="x", padx=5, pady=2)

    def odtworz_film_w_aplikacji(self, sciezka_pliku):
        if self.player is None:
            print("Brak VLC! Otwieram domyślnie...")
            os.startfile(sciezka_pliku)
            return

        print(f"Odtwarzam: {sciezka_pliku}")

        nazwa_filmu = os.path.basename(sciezka_pliku)
        self.lbl_tytul.configure(text=f"Teraz odtwarzane: {nazwa_filmu}", text_color="white")
        self.btn_play.configure(state="normal", text="⏸ Pause")
        self.btn_stop.configure(state="normal")

        self.player.stop()

        media = self.vlc_instance.media_new(sciezka_pliku)
        self.player.set_media(media)

        if sys.platform.startswith('win'):
            self.player.set_hwnd(self.video_screen.winfo_id())

        self.player.play()

    def toggle_play(self):
        if self.player is None: return

        if self.player.is_playing():
            self.player.pause()
            self.btn_play.configure(text="▶ Play")
        else:
            self.player.play()
            self.btn_play.configure(text="⏸ Pause")

    def stop_video(self):
        if self.player is None: return

        self.player.stop()
        self.lbl_tytul.configure(text="Zatrzymano", text_color="gray")
        self.btn_play.configure(state="disabled", text="▶ Play")
        self.btn_stop.configure(state="disabled")

    def destroy(self):
        if self.player:
            self.player.stop()
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
