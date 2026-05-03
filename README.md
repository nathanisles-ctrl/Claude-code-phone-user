# 🎬 Creative Video Studio

A mobile-friendly, self-hosted video production studio that combines **Higgsfield AI** video generation, **ElevenLabs** voiceovers, and **Notion** project management into one warm, cinematic web app.

---

## Features

- **Higgsfield AI** — Generate cinematic videos with Veo 3, Seedance 2, Kling 3.0, Sora 2, and Wan 2.7
- **ElevenLabs** — Auto-generate character voiceovers from `[Character]: "dialogue"` scripts
- **Caption Generation** — Burn-in SRT subtitles synced to voiceover timing
- **Notion Integration** — Auto-create or import Characters & Scenes databases; status updates sync back automatically
- **Scene Continuity** — Use the previous scene's final frame as a reference for visual continuity
- **Video Assembly** — Combine video + audio + captions into a single MP4 via ffmpeg
- **Mobile-first UI** — Warm amber/rust design, works great on phone browsers

---

## Quick Start

### 1. Install

```bash
git clone <repo-url> video-studio
cd video-studio
python setup.py        # interactive setup wizard
```

The wizard will:
- Check Python 3.9+ and ffmpeg
- Install all pip dependencies
- Walk you through creating `.env`
- Create the `uploads/` directory tree

### 2. Environment Setup (`.env`)

Copy `.env.example` to `.env` and fill in:

```env
NOTION_API_KEY=secret_...           # Required — get from notion.so/my-integrations
HIGGSFIELD_API_ID=5e328565-...      # Pre-configured
HIGGSFIELD_API_SECRET=fcf63d4b...   # Pre-configured
ELEVENLABS_API_KEY=b20628fa...      # Pre-configured
SERVER_PORT=8000
SERVER_HOST=0.0.0.0
```

Only `NOTION_API_KEY` needs to be filled in by hand — the other three are pre-configured.

### 3. Install System Dependency

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg -y

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

### 4. Run

```bash
python main.py
```

Server starts at `http://0.0.0.0:8000` by default.

---

## Connecting Notion

### Option A — Auto Setup (recommended for new projects)
1. Go to **Settings → Connect Notion**
2. Paste your Notion Integration Token (`secret_…`)
3. Paste the ID of the Notion page where databases should be created
4. Click **Create Databases** — two databases (Characters, Scenes) are created automatically

### Option B — Import Existing Databases
1. Go to **Settings → Connect Notion → Import Existing**
2. Paste your token and the IDs of your existing Characters and Scenes databases
3. Click **Import & Sync** — all pages are pulled into the local SQLite database

**Getting a Notion Integration Token:**
1. Visit [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **New integration**, give it a name, select your workspace
3. Copy the **Internal Integration Token**
4. Open the Notion page where you want databases, click **⋯ → Add connections** and add your integration

**Getting a Page ID:**  
From a Notion page URL `https://www.notion.so/My-Page-abc123def456`, the ID is `abc123def456`.

---

## Accessing from Your Phone

1. Make sure your phone is on the **same Wi-Fi network** as the computer running the server
2. Find your computer's local IP:
   ```bash
   # macOS / Linux
   ip route get 1 | awk '{print $7}'
   # or
   hostname -I | awk '{print $1}'
   ```
3. Open on your phone: `http://192.168.X.X:8000`

For VPS deployment, open port 8000 in your firewall and access via your server's public IP.

---

## Script Format for Voiceovers

Dialogue scripts should use this format so ElevenLabs knows which voice to use per character:

```
[Alice]: "We need to move now, the window is closing."
[Bob]: "I know, but we can't leave without the files."
[Alice]: "Then we have five minutes. Go."
```

- Characters must be added to the **Cast** tab with their ElevenLabs Voice IDs
- Lines without a character tag are treated as narrator/voiceover

---

## Model Recommendations

| Scene Type  | Recommended Model | Description                          |
|-------------|-------------------|--------------------------------------|
| Dialogue    | Veo 3             | Best realism for conversations       |
| Action      | Seedance 2        | High-motion, dynamic cinematography  |
| Transition  | Kling 3.0         | Smooth, aesthetic transitions        |
| Voiceover   | Veo 3             | Clean backgrounds for VO scenes      |
| Montage     | Sora 2            | Multi-clip, varied movement          |

The app auto-suggests the right model when you pick a scene type.

---

## API Reference

| Method | Endpoint                       | Description                          |
|--------|--------------------------------|--------------------------------------|
| POST   | `/api/setup`                   | Auto-create Notion databases         |
| POST   | `/api/import-notion`           | Import existing Notion workspace     |
| GET    | `/api/projects`                | List all projects                    |
| POST   | `/api/projects`                | Create project                       |
| GET    | `/api/characters`              | List characters (filter by project)  |
| POST   | `/api/characters`              | Add character                        |
| GET    | `/api/scenes`                  | List scenes (filter by project)      |
| POST   | `/api/scenes`                  | Add scene                            |
| PUT    | `/api/scenes/{id}`             | Update scene                         |
| POST   | `/api/generate-video`          | Start video generation job           |
| GET    | `/api/generate-video/{job_id}` | Poll job status                      |
| GET    | `/api/video-jobs`              | List all video jobs                  |
| POST   | `/api/generate-audio`          | Generate voiceover                   |
| GET    | `/api/audio-jobs`              | List all audio jobs                  |
| GET    | `/api/download/{job_id}`       | Download assembled video             |
| GET    | `/api/voices`                  | List available ElevenLabs voices     |
| GET    | `/api/models`                  | List Higgsfield models               |
| GET    | `/api/status`                  | Check all API connection statuses    |
| GET    | `/api/settings`                | Get current settings                 |
| POST   | `/api/settings`                | Update API keys                      |

---

## Troubleshooting

**"ffmpeg not found"**  
Install ffmpeg (see Step 3 above). Video assembly (combining video + audio + captions) requires ffmpeg, but video generation itself still works without it.

**"Notion API error 401"**  
Your token is wrong or expired. Regenerate it at [notion.so/my-integrations](https://www.notion.so/my-integrations) and update it in Settings.

**"Notion API error 404 on page"**  
The page ID in the setup form is incorrect, or you haven't shared the page with your integration. Open the page in Notion → **⋯ → Add connections** → select your integration.

**"Higgsfield error 401"**  
The pre-configured API credentials may have changed. Update them in Settings with your current Higgsfield API ID and Secret.

**Videos stuck in "polling" status**  
Higgsfield generation can take 2–10 minutes depending on the model and duration. The job will auto-update via WebSocket when complete. You can also manually refresh by navigating to the Jobs tab.

**Can't access from phone**  
- Ensure both devices are on the same WiFi network
- Check your firewall allows port 8000: `sudo ufw allow 8000` (Ubuntu)
- Try disabling VPN on either device

**Port already in use**  
Change `SERVER_PORT` in `.env` to another port (e.g. `8001`).

---

## Project Structure

```
video-studio/
├── main.py               # FastAPI server, all API endpoints
├── config.py             # API keys, paths, model config
├── database.py           # SQLite helpers
├── notion_manager.py     # Notion API: create DBs, query, update
├── video_generator.py    # Higgsfield AI: generate + poll status
├── voiceover_generator.py# ElevenLabs: voices, TTS, dialogue parsing
├── caption_generator.py  # SRT/ASS subtitle generation
├── video_assembler.py    # ffmpeg: video + audio + captions → MP4
├── setup.py              # Interactive setup wizard
├── requirements.txt      # Python dependencies
├── .env.example          # Environment template
├── static/
│   ├── index.html        # App shell
│   ├── style.css         # Warm amber theme
│   └── app.js            # Full SPA (vanilla JS)
├── uploads/
│   ├── audio/            # Generated MP3 voiceovers + SRT files
│   ├── video/            # Downloaded raw video files
│   └── assembled/        # Final assembled MP4s
└── studio.db             # SQLite database (auto-created)
```

---

## VPS Deployment

```bash
# Install dependencies
sudo apt update && sudo apt install python3 python3-pip ffmpeg -y

# Clone and setup
git clone <repo-url> /opt/video-studio
cd /opt/video-studio
pip3 install -r requirements.txt
cp .env.example .env && nano .env   # fill in NOTION_API_KEY

# Run with systemd (optional)
sudo nano /etc/systemd/system/video-studio.service
```

```ini
[Unit]
Description=Creative Video Studio
After=network.target

[Service]
WorkingDirectory=/opt/video-studio
ExecStart=/usr/bin/python3 main.py
Restart=always
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable video-studio
sudo systemctl start video-studio
```

Access at `http://YOUR_SERVER_IP:8000`.
