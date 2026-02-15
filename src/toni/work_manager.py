"""Work directory and manifest management for resumable processing."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MANIFEST_VERSION = "1.0"


@dataclass
class ChunkStatus:
    status: str = "pending"
    error: str | None = None
    retries: int = 0
    sub_chunks: list[str] | None = None


@dataclass
class Manifest:
    version: str = MANIFEST_VERSION
    input_file: str = ""
    output_file: str = ""
    model: str = ""
    voice_file: str | None = None
    sample_rate: int = 0
    chunk_pause_ms: int = 500
    total_chunks: int = 0
    chunks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "model": self.model,
            "voice_file": self.voice_file,
            "sample_rate": self.sample_rate,
            "chunk_pause_ms": self.chunk_pause_ms,
            "total_chunks": self.total_chunks,
            "chunks": self.chunks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        return cls(
            version=data.get("version", MANIFEST_VERSION),
            input_file=data.get("input_file", ""),
            output_file=data.get("output_file", ""),
            model=data.get("model", ""),
            voice_file=data.get("voice_file"),
            sample_rate=data.get("sample_rate", 0),
            chunk_pause_ms=data.get("chunk_pause_ms", 500),
            total_chunks=data.get("total_chunks", 0),
            chunks=data.get("chunks", {}),
        )


class WorkManager:
    """Manages work directory structure and progress tracking."""

    def __init__(self, output_path: Path, work_base: Path | None = None):
        self.output_path = output_path
        self.output_stem = output_path.stem

        if work_base is None:
            work_base = Path("./work")

        self.work_dir = work_base / self.output_stem
        self.chunks_dir = self.work_dir / "chunks"
        self.audio_dir = self.work_dir / "audio"
        self.manifest_path = self.work_dir / "manifest.json"
        self._manifest: Manifest | None = None

    def setup(self) -> None:
        """Create work directory structure."""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(exist_ok=True)
        self.audio_dir.mkdir(exist_ok=True)

    def has_existing_run(self) -> bool:
        """Check if a previous run exists."""
        return self.manifest_path.exists()

    def load_manifest(self) -> Manifest:
        """Load manifest from disk or create new one."""
        if self._manifest is not None:
            return self._manifest

        if self.manifest_path.exists():
            with open(self.manifest_path, "r") as f:
                data = json.load(f)
            self._manifest = Manifest.from_dict(data)
        else:
            self._manifest = Manifest()

        return self._manifest

    def save_manifest(self) -> None:
        """Save manifest to disk."""
        if self._manifest is None:
            return

        with open(self.manifest_path, "w") as f:
            json.dump(self._manifest.to_dict(), f, indent=2)

    def init_manifest(
        self,
        input_file: Path,
        output_file: Path,
        model: str,
        voice_file: Path | None,
        sample_rate: int,
        chunk_pause_ms: int,
        total_chunks: int,
    ) -> Manifest:
        """Initialize a new manifest with run parameters."""
        self._manifest = Manifest(
            version=MANIFEST_VERSION,
            input_file=str(input_file),
            output_file=str(output_file),
            model=model,
            voice_file=str(voice_file) if voice_file else None,
            sample_rate=sample_rate,
            chunk_pause_ms=chunk_pause_ms,
            total_chunks=total_chunks,
            chunks={},
        )

        for i in range(total_chunks):
            self._manifest.chunks[str(i)] = {"status": "pending"}

        self.save_manifest()
        return self._manifest

    def get_chunk_text_path(self, chunk_id: str) -> Path:
        """Get path for a chunk's text file."""
        return self.chunks_dir / f"{chunk_id}.txt"

    def get_chunk_audio_path(self, chunk_id: str) -> Path:
        """Get path for a chunk's audio file."""
        return self.audio_dir / f"{chunk_id}.wav"

    def save_chunk_text(self, chunk_id: str, text: str) -> None:
        """Save chunk text to file."""
        path = self.get_chunk_text_path(chunk_id)
        path.write_text(text, encoding="utf-8")

    def load_chunk_text(self, chunk_id: str) -> str:
        """Load chunk text from file."""
        path = self.get_chunk_text_path(chunk_id)
        return path.read_text(encoding="utf-8")

    def get_chunk_status(self, chunk_id: str) -> str:
        """Get status of a chunk."""
        manifest = self.load_manifest()
        chunk_data = manifest.chunks.get(str(chunk_id), {})
        return chunk_data.get("status", "pending")

    def set_chunk_status(
        self,
        chunk_id: str,
        status: str,
        error: str | None = None,
        sub_chunks: list[str] | None = None,
    ) -> None:
        """Update chunk status."""
        manifest = self.load_manifest()

        if str(chunk_id) not in manifest.chunks:
            manifest.chunks[str(chunk_id)] = {}

        chunk_data = manifest.chunks[str(chunk_id)]
        chunk_data["status"] = status

        if error is not None:
            chunk_data["error"] = error
        elif "error" in chunk_data and status == "completed":
            del chunk_data["error"]

        if sub_chunks is not None:
            chunk_data["sub_chunks"] = sub_chunks

        if status == "failed":
            chunk_data["retries"] = chunk_data.get("retries", 0) + 1

        self.save_manifest()

    def increment_retries(self, chunk_id: str) -> int:
        """Increment retry count for a chunk and return new count."""
        manifest = self.load_manifest()
        chunk_data = manifest.chunks.get(str(chunk_id), {})
        retries = chunk_data.get("retries", 0) + 1
        chunk_data["retries"] = retries
        manifest.chunks[str(chunk_id)] = chunk_data
        self.save_manifest()
        return retries

    def get_retries(self, chunk_id: str) -> int:
        """Get retry count for a chunk."""
        manifest = self.load_manifest()
        chunk_data = manifest.chunks.get(str(chunk_id), {})
        return chunk_data.get("retries", 0)

    def get_pending_chunks(self) -> list[str]:
        """Get list of chunk IDs that are pending."""
        manifest = self.load_manifest()
        return [
            chunk_id
            for chunk_id, data in manifest.chunks.items()
            if data.get("status") == "pending"
        ]

    def get_completed_chunks(self) -> list[str]:
        """Get list of chunk IDs that are completed."""
        manifest = self.load_manifest()
        return [
            chunk_id
            for chunk_id, data in manifest.chunks.items()
            if data.get("status") == "completed"
        ]

    def get_failed_chunks(self) -> list[str]:
        """Get list of chunk IDs that failed."""
        manifest = self.load_manifest()
        return [
            chunk_id
            for chunk_id, data in manifest.chunks.items()
            if data.get("status") == "failed"
        ]

    def get_split_chunks(self) -> list[str]:
        """Get list of chunk IDs that were split into sub-chunks."""
        manifest = self.load_manifest()
        return [
            chunk_id
            for chunk_id, data in manifest.chunks.items()
            if data.get("status") == "split"
        ]

    def add_sub_chunk(self, parent_id: str, sub_id: str, text: str) -> None:
        """Add a sub-chunk created from splitting a failed chunk."""
        manifest = self.load_manifest()

        parent_data = manifest.chunks.get(str(parent_id), {})
        sub_chunks = parent_data.get("sub_chunks", [])
        if sub_id not in sub_chunks:
            sub_chunks.append(sub_id)
        parent_data["sub_chunks"] = sub_chunks
        parent_data["status"] = "split"
        manifest.chunks[str(parent_id)] = parent_data

        manifest.chunks[sub_id] = {"status": "pending", "parent": str(parent_id)}

        self.save_chunk_text(sub_id, text)
        self.save_manifest()

    def get_all_audio_chunks_ordered(self) -> list[str]:
        """Get all chunk IDs that have audio, in correct order for concatenation."""
        manifest = self.load_manifest()
        result = []

        def sort_key(chunk_id: str) -> tuple:
            parts = chunk_id.replace("_", ".").split(".")
            return tuple(
                int(p) if p.isdigit() else ord(p[0]) if p else 0 for p in parts
            )

        for i in range(manifest.total_chunks):
            chunk_id = str(i)
            chunk_data = manifest.chunks.get(chunk_id, {})
            status = chunk_data.get("status", "pending")

            if status == "completed":
                audio_path = self.get_chunk_audio_path(chunk_id)
                if audio_path.exists():
                    result.append(chunk_id)
            elif status == "split":
                sub_chunks = chunk_data.get("sub_chunks", [])
                sorted_subs = sorted(sub_chunks, key=sort_key)
                for sub_id in sorted_subs:
                    sub_data = manifest.chunks.get(sub_id, {})
                    if sub_data.get("status") == "completed":
                        audio_path = self.get_chunk_audio_path(sub_id)
                        if audio_path.exists():
                            result.append(sub_id)

        return result

    def get_progress_summary(self) -> dict:
        """Get summary of processing progress."""
        manifest = self.load_manifest()

        completed = 0
        failed = 0
        pending = 0
        split = 0

        for chunk_data in manifest.chunks.values():
            status = chunk_data.get("status", "pending")
            if status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
            elif status == "pending":
                pending += 1
            elif status == "split":
                split += 1

        return {
            "total": manifest.total_chunks,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "split": split,
        }
