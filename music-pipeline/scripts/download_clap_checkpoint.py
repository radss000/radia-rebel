import sys
import urllib.request
from pathlib import Path

CHECKPOINT_URL = (
    "https://huggingface.co/lukewys/laion_clap/resolve/main/"
    "music_audioset_epoch_15_esc_90.14.pt"
)
CHECKPOINT_NAME = "music_audioset_epoch_15_esc_90.14.pt"
MIN_SIZE_MB = 2100
MAX_SIZE_MB = 2400


def _download_with_progress(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    tmp_path = destination.with_suffix(destination.suffix + ".part")
    downloaded = 0
    next_report = 0.1

    with urllib.request.urlopen(request) as response:
        total = response.headers.get("Content-Length")
        total_size = int(total) if total else None
        with tmp_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    progress = downloaded / total_size
                    if progress >= next_report or downloaded == total_size:
                        percent = int(progress * 100)
                        print(f"Download {percent}%")
                        next_report += 0.1
                else:
                    if downloaded // (50 * 1024 * 1024) > (
                        (downloaded - len(chunk)) // (50 * 1024 * 1024)
                    ):
                        print(f"Downloaded {downloaded / (1024 * 1024):.1f}MB")

    tmp_path.replace(destination)


def main() -> int:
    script_root = Path(__file__).resolve().parents[1]
    checkpoint_dir = script_root / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / CHECKPOINT_NAME

    if checkpoint_path.exists():
        size_mb = checkpoint_path.stat().st_size / (1024 * 1024)
        if MIN_SIZE_MB <= size_mb <= MAX_SIZE_MB:
            print(f"Checkpoint déjà présent : {size_mb:.1f}MB à {checkpoint_path}")
            return 0
        checkpoint_path.unlink()

    try:
        _download_with_progress(CHECKPOINT_URL, checkpoint_path)
    except Exception:
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        part_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".part")
        if part_path.exists():
            part_path.unlink()
        raise

    size_mb = checkpoint_path.stat().st_size / (1024 * 1024)
    if not (MIN_SIZE_MB <= size_mb <= MAX_SIZE_MB):
        raise ValueError(
            f"Taille inattendue: {size_mb:.1f}MB (attendu {MIN_SIZE_MB}-{MAX_SIZE_MB}MB)"
        )

    print(f"Checkpoint téléchargé : {size_mb:.1f}MB à {checkpoint_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Download interrompu.")
        sys.exit(1)
