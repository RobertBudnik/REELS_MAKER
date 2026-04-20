import os
import whisper
import warnings

# Konfiguracja ImageMagick (tylko Windows)
if os.name == 'nt':
    IMAGEMAGICK_PATH = r"C:\Program Files\ImageMagick-7.1.2-Q16-HDRI\magick.exe"
    if not os.path.exists(IMAGEMAGICK_PATH):
        alternatywy = [
            r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
            r"C:\Program Files\ImageMagick-7.0.11-Q16-HDRI\magick.exe",
            r"C:\Program Files (x86)\ImageMagick-7.1.2-Q16-HDRI\magick.exe",
        ]
        for alt in alternatywy:
            if os.path.exists(alt):
                IMAGEMAGICK_PATH = alt
                print(f"✅ Znaleziono ImageMagick pod alternatywną ścieżką: {alt}")
                break
        else:
            print("⚠️ UWAGA: Nie znaleziono ImageMagick! TextClip może nie działać.")
            print("Pobierz ze: https://imagemagick.org/script/download.php#windows")

    os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_PATH

try:
    from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
except ImportError:
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip

warnings.filterwarnings("ignore")


def stworz_text_clip(text, font_file, font_size, color, stroke_color=None, stroke_width=0, video_width=None):
    """Tworzy instancję TextClip z bezpieczną obsługą starego i nowego API MoviePy"""
    try:
        # Pół-nowe / stare API
        clip = TextClip(
            txt=text,
            fontsize=font_size,
            color=color,
            font=font_file,
            method="caption",
            size=(int(video_width * 0.9), None) if video_width else None,
            align="center",
            stroke_color=stroke_color if stroke_width > 0 else None,
            stroke_width=stroke_width if stroke_width > 0 else 0
        )
    except Exception:
        # Fallback do nowszego API
        clip = TextClip(
            text=text,
            font_size=font_size,
            color=color,
            font=font_file,
            method="caption",
            size=(int(video_width * 0.9), None) if video_width else None,
            align="center",
            stroke_color=stroke_color if stroke_width > 0 else None,
            stroke_width=stroke_width if stroke_width > 0 else 0
        )
    return clip


def aplikuj_pozycje_i_czas(clip, start, end):
    """Bezpieczne przypisywanie czasu i pozycji dla różnych wersji MoviePy"""
    try:
        return clip.set_position(('center', 'center')).set_start(start).set_end(end)
    except AttributeError:
        return clip.with_position(('center', 'center')).with_start(start).with_end(end)


def add_viral_subtitles(video_path, output_path, model):
    print(f"\n🎙️ Precyzyjna transkrypcja: {os.path.basename(video_path)}...")
    result = model.transcribe(video_path, language="pl", word_timestamps=True)

    print("🎬 Generowanie profesjonalnych napisów...")
    video = None
    final_video = None

    try:
        video = VideoFileClip(video_path)
        subtitle_clips = []

        font_file = 'FredokaOne-Regular.ttf'
        font_size = 100

        if not os.path.exists(font_file):
            print(f"⚠️ Brak czcionki '{font_file}'! Używam domyślnej czcionki systemowej.")
            font_file = "Arial"

        rainbow_colors = ['#FFD700', '#00FFFF', '#39FF14', '#FF00FF', '#FF6600', 'white']
        word_count = 0

        for segment in result.get('segments', []):
            if 'words' not in segment:
                continue

            for word_info in segment['words']:
                start_time = word_info['start']
                end_time = max(start_time + 0.15, word_info['end'])  # Minimalny czas 0.15s
                text = word_info['word'].strip().upper()

                if not text:
                    continue

                current_color = rainbow_colors[word_count % len(rainbow_colors)]
                word_count += 1

                try:
                    outline_clip = stworz_text_clip(text, font_file, font_size, 'black', 'black', 18, video.w)
                    outline_clip = aplikuj_pozycje_i_czas(outline_clip, start_time, end_time)

                    fill_clip = stworz_text_clip(text, font_file, font_size, current_color, video_width=video.w)
                    fill_clip = aplikuj_pozycje_i_czas(fill_clip, start_time, end_time)

                    subtitle_clips.extend([outline_clip, fill_clip])
                except Exception as e:
                    print(f"⚠️ Pominięto słowo '{text}' z powodu błędu MoviePy: {e}")

        if not subtitle_clips:
            print("⚠️ Nie wygenerowano napisów. Zapisuję oryginał.")
            video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=video.fps, logger=None)
            return

        final_video = CompositeVideoClip([video] + subtitle_clips)

        print(f"💾 Zapisywanie: {output_path}...")
        final_video.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            fps=video.fps,
            threads=4,
            logger=None
        )
        print("✅ Gotowe!")

    except Exception as e:
        print(f"❌ Błąd podczas przetwarzania {video_path}: {e}")
    finally:
        # Zamykanie zasobów
        if video: video.close()
        if final_video: final_video.close()
        # Zamykanie klipów z napisami, jeśli to możliwe
        try:
            for clip in subtitle_clips: clip.close()
        except:
            pass


def process_folder(input_folder, output_folder):
    if not os.path.exists(input_folder):
        os.makedirs(input_folder)
        print(f"📁 Utworzono folder '{input_folder}'. Wrzuć do niego filmy i uruchom skrypt ponownie.")
        return

    os.makedirs(output_folder, exist_ok=True)
    supported_formats = ('.mp4', '.mov', '.mkv', '.avi')
    video_files = [f for f in os.listdir(input_folder) if f.lower().endswith(supported_formats)]

    if not video_files:
        print(f"⚠️ Nie znaleziono żadnych filmów w folderze '{input_folder}'.")
        return

    print(f"👀 Znaleziono {len(video_files)} filmów do przetworzenia.")
    print("⏳ Ładowanie modelu AI (Whisper)... To potrwa tylko chwilę.")
    model = whisper.load_model("small")

    for index, filename in enumerate(video_files, 1):
        print(f"\n--- Przetwarzanie filmu {index} z {len(video_files)} ---")
        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, f"gotowe_{filename}")

        if os.path.exists(output_path):
            print(f"⏭️ Pominięto (już istnieje): gotowe_{filename}")
            continue

        add_viral_subtitles(input_path, output_path, model)

    print("\n🎉 Wszystkie filmy zostały pomyślnie przetworzone!")


if __name__ == "__main__":
    process_folder("gotowe_filmy", "filmy")