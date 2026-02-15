#!/bin/bash
set -e

echo "Installing Toni the Book Maker..."

if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
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
echo "To install a TTS model (choose one - they have conflicting deps):"
echo "  Pocket TTS (CPU, recommended): uv sync --extra pocket"
echo "  Kani TTS 2 (GPU):              uv sync --extra kani"
echo ""
echo "Usage: ./run.sh -i <input.pdf> -o <output.mp3>"
