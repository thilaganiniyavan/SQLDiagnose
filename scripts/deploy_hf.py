# deploy_hf.py
# Deploys SQLDiagnose to a Hugging Face Docker Space (needs a write token: `hf auth login`).
#
#   python scripts/deploy_hf.py                  # -> https://huggingface.co/spaces/<user>/SQLDiagnose
#   python scripts/deploy_hf.py --skip-examples  # don't (re)upload the example databases
#
# 1. uploads the example SQLite databases (Spider, make data) to the dataset <user>/sqldiagnose-example-dbs
# 2. uploads the committed code (git HEAD) to the Space, with deployment/huggingface/Dockerfile as its Dockerfile
#    and a Space card on top of README.md; the Space then builds and starts on its own

import argparse
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DB_DIR = ROOT / "data" / "raw" / "spider_data" / "database"
EXCLUDE = ("docs/case_study/", "reports/ieee/", "notebooks/")   # not needed by the running app

SPACE_CARD = """---
title: SQLDiagnose
emoji: 🩺
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
short_description: Diagnose, explain and repair SQL; verified text-to-SQL
---

"""

EXAMPLES_CARD = """---
license: cc-by-sa-4.0
pretty_name: SQLDiagnose example databases
---

# SQLDiagnose example databases

SQLite databases of the [Spider](https://yale-lily.github.io/spider) benchmark (Yu et al., EMNLP 2018),
redistributed under CC BY-SA 4.0 so the [SQLDiagnose](https://github.com/thilaganiniyavan/SQLDiagnose) web app
can run queries against the example schemas.
"""


def stage_code(dest: Path) -> None:
    """Extracts the committed tree (HEAD) into dest, without the paths in EXCLUDE."""
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, check=True,
                             capture_output=True).stdout
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        members = [m for m in tar.getmembers() if not m.name.startswith(EXCLUDE)]
        tar.extractall(dest, members=members, filter="data")
    (dest / "Dockerfile").write_bytes((ROOT / "deployment" / "huggingface" / "Dockerfile").read_bytes())
    (dest / "README.md").write_text(SPACE_CARD + (dest / "README.md").read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--space", default="SQLDiagnose", help="Space name (under your account)")
    ap.add_argument("--examples", default="sqldiagnose-example-dbs", help="dataset name for the example databases")
    ap.add_argument("--skip-examples", action="store_true")
    args = ap.parse_args()

    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
        print("Note: uncommitted changes are not deployed; the Space gets git HEAD.")

    api = HfApi()
    user = api.whoami()["name"]
    space_id, examples_id = f"{user}/{args.space}", f"{user}/{args.examples}"

    if not args.skip_examples:
        if not EXAMPLE_DB_DIR.is_dir():
            sys.exit(f"{EXAMPLE_DB_DIR} not found; run `make data` first or pass --skip-examples.")
        api.create_repo(examples_id, repo_type="dataset", exist_ok=True)
        api.upload_file(path_or_fileobj=EXAMPLES_CARD.encode(), path_in_repo="README.md",
                        repo_id=examples_id, repo_type="dataset")
        print(f"Uploading example databases to datasets/{examples_id} ...")
        api.upload_folder(folder_path=EXAMPLE_DB_DIR, repo_id=examples_id, repo_type="dataset",
                          allow_patterns=["*/*.sqlite"], commit_message="Example databases")

    api.create_repo(space_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_variable(space_id, "EXAMPLES_REPO", examples_id)
    with tempfile.TemporaryDirectory() as tmp:
        stage_code(Path(tmp))
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
        print(f"Uploading code ({head}) to spaces/{space_id} ...")
        api.upload_folder(folder_path=tmp, repo_id=space_id, repo_type="space",
                          commit_message=f"Deploy {head}", delete_patterns="*")
    print(f"Done. The Space builds now: https://huggingface.co/spaces/{space_id}")


if __name__ == "__main__":
    main()
