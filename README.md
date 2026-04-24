# Creative Video Studio

A professional video generation studio with Notion integration, multi-model AI video generation, voiceover sync, and auto-captions — accessible from any device including your phone.

## Features

- **Notion Integration** — Pull content directly from your Notion workspace to drive video scripts and prompts
- **Multi-Model AI Video** — Support for Higgsfield, RunwayML, and other AI video generation models
- **Voiceover Sync** — ElevenLabs integration for realistic AI voiceover generation and audio-video sync
- **Auto-Captions** — Automated subtitle/caption generation and burn-in
- **Phone-Accessible UI** — Responsive web interface optimized for mobile use
- **FastAPI Backend** — High-performance async Python API

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| AI Video | Higgsfield AI, RunwayML |
| Voiceover | ElevenLabs |
| Content Source | Notion API |
| Captions | Whisper / ffmpeg |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | HTML/CSS/JS (mobile-first) |
| Media Processing | ffmpeg, Pillow |

## Prerequisites

- Python 3.11 or higher
- `ffmpeg` installed on your system
- API keys for: Notion, ElevenLabs, Higgsfield (or RunwayML)
- Git

Install ffmpeg:
```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# Windows (via Chocolatey)
choco install ffmpeg
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/creative-video-studio.git
cd creative-video-studio
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create the uploads directory

```bash
mkdir -p uploads output
```

## Configuration

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Server
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Notion
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ElevenLabs
ELEVENLABS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ELEVENLABS_VOICE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Higgsfield
HIGGSFIELD_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# RunwayML (optional alternative)
RUNWAYML_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Storage
UPLOAD_DIR=uploads
OUTPUT_DIR=output
MAX_FILE_SIZE_MB=500

# Database
DATABASE_URL=sqlite:///./studio.sqlite3
```

### Finding Your Notion IDs

1. **API Key**: Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → Create integration → copy the secret
2. **Database ID**: Open your Notion database in browser — the ID is the 32-character string in the URL before the `?`
3. Share the database with your integration in Notion (click Share → invite your integration)

## Running Locally

```bash
# With the virtual environment activated:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The studio will be available at:
- Local: `http://localhost:8000`
- Network (for phone): `http://YOUR_LOCAL_IP:8000`

Find your local IP:
```bash
# macOS / Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig | findstr "IPv4"
```

## Accessing from Your Phone

1. Make sure your phone and computer are on the **same Wi-Fi network**
2. Start the server with `--host 0.0.0.0` (already set in the run command above)
3. Find your computer's local IP address (e.g. `192.168.1.42`)
4. Open your phone browser and go to: `http://192.168.1.42:8000`

For permanent phone access outside your home network, consider:
- [ngrok](https://ngrok.com/) for a quick public tunnel: `ngrok http 8000`
- Deploy to a VPS (DigitalOcean, Fly.io, Railway)

## API Documentation

Once the server is running, interactive API docs are available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Studio web UI |
| `GET` | `/health` | Health check |
| `GET` | `/api/notion/pages` | List Notion pages |
| `POST` | `/api/video/generate` | Generate a video |
| `POST` | `/api/voiceover/generate` | Generate voiceover audio |
| `POST` | `/api/captions/generate` | Generate captions for a video |
| `GET` | `/api/jobs/{job_id}` | Check job status |
| `GET` | `/api/outputs` | List generated outputs |

### Example: Generate a Video

```bash
curl -X POST http://localhost:8000/api/video/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A cinematic sunset over ocean waves",
    "model": "higgsfield",
    "duration": 5,
    "resolution": "1080p"
  }'
```

## Project Structure

```
creative-video-studio/
├── main.py                  # FastAPI app entry point
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore
├── LICENSE
├── README.md
├── routers/
│   ├── video.py             # Video generation endpoints
│   ├── voiceover.py         # ElevenLabs voiceover endpoints
│   ├── captions.py          # Caption generation endpoints
│   └── notion.py            # Notion API endpoints
├── services/
│   ├── higgsfield.py        # Higgsfield AI client
│   ├── runway.py            # RunwayML client
│   ├── elevenlabs.py        # ElevenLabs client
│   ├── notion.py            # Notion client
│   └── captions.py          # Whisper/ffmpeg caption service
├── models/
│   └── schemas.py           # Pydantic request/response models
├── static/
│   ├── index.html           # Mobile-first studio UI
│   ├── css/
│   └── js/
├── uploads/                 # User uploaded files (gitignored)
└── output/                  # Generated videos/audio (gitignored)
```

## Troubleshooting

**Server won't start**
- Check that your `.env` file exists and has valid values
- Ensure virtual environment is activated (`source venv/bin/activate`)
- Confirm port 8000 is not in use: `lsof -i :8000`

**Can't connect from phone**
- Verify both devices are on the same Wi-Fi network
- Confirm server was started with `--host 0.0.0.0`
- Check firewall isn't blocking port 8000

**Notion API errors**
- Re-check that your integration has been shared with the target database
- Database IDs must be 32 hex characters with no dashes

**Video generation fails**
- Confirm your Higgsfield/RunwayML API key has available credits
- Check job status via `GET /api/jobs/{job_id}` — generation can take 1–5 minutes

**ffmpeg not found**
- Run `ffmpeg -version` to confirm it's installed and on your PATH
- On macOS, re-run `brew install ffmpeg`

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to your branch: `git push origin feature/your-feature-name`
5. Open a Pull Request

Please follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

## License

MIT — see [LICENSE](LICENSE) for details.
