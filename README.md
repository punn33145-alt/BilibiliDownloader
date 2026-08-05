# Bilibili Video Downloader



A modern Windows desktop application for downloading Bilibili videos with the simplest possible workflow. Paste a URL, choose a save folder, and click **Download** — everything else is fully automatic.



![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)

![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)

![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp-orange.svg)



## Features



### Module 1 — Video Downloader (primary)



- **Simple 3-step workflow** — URL, save folder, download

- **Automatic best quality** — `bestvideo+bestaudio` merged to MP4

- **Smart subtitle selection** — priority: Vietnamese → Chinese → English

- **Organized output** — each video saved in its own titled folder

- **Live preview** — title, thumbnail, and duration fetched automatically

- **Real-time progress** — percentage, speed, ETA, and downloaded size

- **Non-blocking UI** — downloads run in background threads

- **Fast startup** — no AI, no model downloads, no HuggingFace at launch

- **Dark theme** — clean, professional interface

- **Drag & drop** — drop Bilibili URLs onto the window

- **Clipboard detection** — auto-pastes valid Bilibili URLs from clipboard

- **Remembers save folder** — persists your last used directory

- **Notifications** — system tray notification when download completes

- **Opens folder** — automatically opens the save folder after completion



### Module 2 — Optional Translation (on demand)



- **Separate from downloading** — translation never runs during download

- **Translate Subtitle button** — loads AI engine only when you click it

- **Offline zh → vi** — local neural models, no cloud APIs

- **Optional install** — core app works without PyTorch or Transformers



## Output Files



After a successful video download, a folder is created named after the video title:



```

Video Title/

    Video Title.mp4

    Video Title.vi.srt   (if Vietnamese subtitles available)

    Video Title.zh.srt   (if only Chinese subtitles available)

    Thumbnail.jpg

    README.txt

```



If you later translate a Chinese subtitle, `Video Title.vi.srt` is created alongside the `.zh.srt` file.



## Offline Translation (Optional)



Chinese subtitles can be translated to Vietnamese using a **fully local** open-source neural model. This is a separate feature — click **Translate Subtitle** after download (or pick any `.zh.srt` file).



**Model priority (automatic selection):**



1. Meta NLLB-200 (`facebook/nllb-200-distilled-600M`)

2. Facebook M2M100 (`facebook/m2m100_418M`, then `m2m100_1.2B` as fallback)

3. MarianMT (`Helsinki-NLP/opus-mt-zh-vi`)



Models are stored locally in the project folder:



```

D:\Download_VD_Bilibili\models\

```



## Requirements



| Dependency | Purpose |

|---|---|

| Python 3.12+ | Runtime |

| PySide6 | GUI framework |

| yt-dlp | Download engine (Python API) |

| requests | Thumbnail fetching |

| Pillow | Image processing |

| FFmpeg | Stream merging (system install) |

| certifi + truststore | HTTPS on Windows |



**Optional (translation only):** transformers, torch, sentencepiece, safetensors, huggingface-hub — install via `requirements-translate.txt`.



### Install FFmpeg (Windows)



1. Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) (or use `winget install Gyan.FFmpeg`)

2. Add the `bin` folder to your system **PATH**

3. Verify: `ffmpeg -version`



## Installation



### 1. Clone or download this project



```powershell

cd D:\Download_VD_Bilibili

```



### 2. Create a virtual environment (recommended)



```powershell

py -3 -m venv .venv

.\.venv\Scripts\Activate.ps1

```



### 3. Install core dependencies



```powershell

py -3 -m pip install -r requirements.txt

```



### 4. (Optional) Install translation dependencies



Only needed if you want the **Translate Subtitle** feature:



```powershell

py -3 -m pip install -r requirements-translate.txt

```



### 5. Generate the application icon (first time only)



```powershell

py -3 scripts\generate_icon.py

```



### 6. Run the application



```powershell

py -3 app\main.py

```



Startup loads only the GUI and configuration — no AI initialization.



## Usage



1. **Paste** a Bilibili video URL (e.g. `https://www.bilibili.com/video/BVxxxxxxxx`)

2. **Choose** a save folder (defaults to your Downloads folder)

3. **Click Download**



The app automatically:



- Fetches video title, thumbnail, and duration

- Downloads the highest quality MP4 into a titled subfolder

- Downloads the best available subtitle (Vietnamese preferred, then Chinese)

- Saves Thumbnail.jpg and README.txt with full video metadata



**Optional:** After download, if a Chinese subtitle was saved, click **Translate Subtitle** to create a Vietnamese `.vi.srt` file.



## Project Structure



```

Download_VD_Bilibili/

├── app/

│   ├── main.py

│   ├── core/              # Shared utilities (paths, SSL, config, logging)

│   ├── downloader/        # Module 1 — video download (no AI)

│   ├── translator/        # Module 2 — optional offline translation

│   ├── ui/

│   │   ├── main_window.py

│   │   └── styles.py

│   └── resources/icons/

├── models/                # Translation models (created on first translate)

├── logs/                  # Application logs

├── scripts/generate_icon.py

├── requirements.txt

├── requirements-translate.txt

├── bilibili_downloader.spec

└── README.md

```



## Packaging into EXE (PyInstaller)



```powershell

py -3 -m pip install -r requirements.txt

py -3 scripts\generate_icon.py

py -3 -m PyInstaller bilibili_downloader.spec

```



Output: `dist\BilibiliVideoDownloader.exe`



The core EXE does **not** bundle PyTorch or translation models. Users who want translation install `requirements-translate.txt` separately.



### Notes for distribution



- **FFmpeg is not bundled** — users must install FFmpeg on PATH

- **Translation models are not bundled** — downloaded on first translate to `models/`

- Core EXE is small and starts quickly without AI dependencies



## Error Handling



| Situation | Behavior |

|---|---|

| Invalid URL | Friendly error message |

| Private / region-blocked video | Clear explanation |

| FFmpeg missing | Warning at startup |

| Missing core Python packages | Install instructions dialog |

| Translation packages missing | Shown only when Translate Subtitle is clicked |

| Disk full / permission denied | Clear error message |



## Logging



```

D:\Download_VD_Bilibili\logs\app.log

```



## License



This project is provided as-is for personal use. Respect Bilibili's terms of service and copyright when downloading content.



## Acknowledgments



- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download engine

- [FFmpeg](https://ffmpeg.org/) — media processing

- [PySide6](https://doc.qt.io/qtforpython/) — GUI framework

- [Hugging Face Transformers](https://huggingface.co/docs/transformers) — optional offline translation models

