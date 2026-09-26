# download_model.py
# Downloads the fine-tuned classifier from the GitHub release and unpacks it where the API expects it.
#
#   python scripts/download_model.py            # -> models/checkpoints/codeberta-small-ft/best
#   python scripts/download_model.py --force    # re-download even if present

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = ("https://github.com/thilaganiniyavan/SQLDiagnose/releases/download/"
               "v1.0/sqldiagnose-classifier.zip")
SHA256 = "abbcaa8bf0a747b66e9846a2ace0cd5f008d970b05584e32a9b71cbbbd42a2b9"
TARGET = ROOT / "models" / "checkpoints" / "codeberta-small-ft"


def download(url: str, dest: Path) -> None:
    last = [-1]

    def progress(blocks, block_size, total):
        if total > 0:
            done = min(blocks * block_size, total)
            pct = int(100 * done / total)
            if pct != last[0]:                       # redraw only when the percentage changes
                last[0] = pct
                sys.stdout.write(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB ({pct}%)")
                sys.stdout.flush()
    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--url", default=RELEASE_URL)
    args = ap.parse_args()

    if (TARGET / "best" / "sqldiagnose_labels.json").exists() and not args.force:
        print(f"Model already present at {TARGET / 'best'} (use --force to re-download).")
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    archive = TARGET / "sqldiagnose-classifier.zip"
    print(f"Downloading {args.url}")
    download(args.url, archive)
    digest = sha256(archive)
    if args.url == RELEASE_URL and digest != SHA256:
        archive.unlink()
        sys.exit(f"Checksum mismatch ({digest}); the download is corrupt. Try again.")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(TARGET)
    archive.unlink()
    print(f"Classifier ready at {TARGET / 'best'}")


if __name__ == "__main__":
    main()
