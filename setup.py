"""
Creative Video Studio — First-run setup wizard.
Run with: python setup.py
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent


def print_banner():
    print("\n" + "=" * 60)
    print("  🎬  Creative Video Studio — Setup Wizard")
    print("=" * 60 + "\n")


def check_python():
    if sys.version_info < (3, 9):
        print("❌  Python 3.9+ is required.")
        sys.exit(1)
    print(f"✓  Python {sys.version_info.major}.{sys.version_info.minor}")


def check_ffmpeg():
    if shutil.which("ffmpeg"):
        print("✓  ffmpeg found")
    else:
        print("⚠  ffmpeg not found — video assembly will be disabled.")
        print("   Install: sudo apt install ffmpeg  (Ubuntu/Debian)")
        print("            brew install ffmpeg       (macOS)")


def install_deps():
    print("\n📦 Installing Python dependencies …")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(BASE_DIR / "requirements.txt"), "--quiet"]
    )
    print("✓  Dependencies installed")


def create_env():
    env_path    = BASE_DIR / ".env"
    example_path = BASE_DIR / ".env.example"

    if env_path.exists():
        overwrite = input("\n.env already exists. Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("⏭  Skipping .env creation")
            return

    print("\n🔑 Configure API keys")
    print("   (Press Enter to keep the pre-configured defaults)\n")

    notion_key = input("Notion API Token (required — get from notion.so/my-integrations): ").strip()
    hf_id      = input(f"Higgsfield API ID     [{default_val('HIGGSFIELD_API_ID')}]: ").strip()
    hf_sec     = input(f"Higgsfield API Secret [{default_val('HIGGSFIELD_API_SECRET')}]: ").strip()
    el_key     = input(f"ElevenLabs API Key    [{default_val('ELEVENLABS_API_KEY')}]: ").strip()
    port       = input("Server port           [8000]: ").strip() or "8000"

    lines = [
        f"NOTION_API_KEY={notion_key}",
        f"HIGGSFIELD_API_ID={hf_id or default_val('HIGGSFIELD_API_ID')}",
        f"HIGGSFIELD_API_SECRET={hf_sec or default_val('HIGGSFIELD_API_SECRET')}",
        f"ELEVENLABS_API_KEY={el_key or default_val('ELEVENLABS_API_KEY')}",
        f"SERVER_PORT={port}",
        "SERVER_HOST=0.0.0.0",
    ]
    env_path.write_text("\n".join(lines) + "\n")
    print(f"✓  .env written to {env_path}")


def default_val(key: str) -> str:
    defaults = {
        "HIGGSFIELD_API_ID":     "5e328565-11ef-4469-9828-80b8b18ab200",
        "HIGGSFIELD_API_SECRET": "fcf63d4b3ec9870b13d81898c0899552fe75c90928f051185585ad004741109",
        "ELEVENLABS_API_KEY":    "b20628fa260535f39389a4d46eaa4d97c9a3f7ed857a8559f3c3a9f72f0923f0",
    }
    return defaults.get(key, "")


def create_dirs():
    for d in ["uploads/audio", "uploads/video", "uploads/assembled"]:
        (BASE_DIR / d).mkdir(parents=True, exist_ok=True)
    print("✓  Upload directories created")


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "YOUR_IP"


def print_next_steps():
    ip   = get_local_ip()
    port = "8000"
    env  = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SERVER_PORT="):
                port = line.split("=", 1)[1].strip()

    print("\n" + "=" * 60)
    print("  ✅  Setup complete!")
    print("=" * 60)
    print(f"\n  Start the server:")
    print(f"    python main.py")
    print(f"\n  Access from your computer:")
    print(f"    http://localhost:{port}")
    print(f"\n  Access from your phone (same WiFi):")
    print(f"    http://{ip}:{port}")
    print("\n  First steps in the app:")
    print("    1. Go to Settings → Connect Notion")
    print("    2. Add characters with their ElevenLabs Voice IDs")
    print("    3. Add scenes with scripts")
    print("    4. Hit Generate!\n")


def main():
    print_banner()
    check_python()
    check_ffmpeg()
    install_deps()
    create_dirs()
    create_env()
    print_next_steps()


if __name__ == "__main__":
    main()
