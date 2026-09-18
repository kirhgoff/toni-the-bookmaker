#!/bin/bash
set -e

echo "Installing Toni the Book Maker..."

if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! command -v bun &> /dev/null; then
    echo "Error: bun is not installed."
    echo "Install it with: curl -fsSL https://bun.sh/install | bash"
    exit 1
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "Warning: ffmpeg is not installed."
    echo "MP3 encoding requires ffmpeg. Install it with:"
    echo "  macOS:  brew install ffmpeg"
    echo "  Linux:  apt install ffmpeg"
    echo ""
fi

echo "Syncing dependencies..."
uv sync

echo ""
echo "Installation complete!"
echo ""
echo "Pick one TTS engine (they have conflicting dependencies):"
echo "  OmniVoice (default, any language, GPU/Apple Silicon): uv sync --extra omni"
echo "  Pocket TTS (English only, CPU):                       uv sync --extra pocket"
echo "  Kani TTS 2 (English only, GPU):                       uv sync --extra kani"
echo ""
echo "Usage: scripts/record_audiobook.sh -i book.txt -v voice.wav -d"
