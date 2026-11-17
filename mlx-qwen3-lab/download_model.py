"""Download a pinned public model snapshot and verify its contents."""

import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parent
REPO = "mlx-community/Qwen3-4B-4bit"
REVISION = "4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25"
DEST = ROOT / "models" / "Qwen3-4B-4bit"


def main():
    info = HfApi().model_info(REPO, revision=REVISION, files_metadata=True)
    print(f"Downloading {REPO}@{REVISION} to {DEST}", flush=True)
    snapshot_download(REPO, revision=REVISION, local_dir=DEST, max_workers=4)
    files = []
    for item in info.siblings:
        path = DEST / item.rfilename
        size = path.stat().st_size
        if item.size is not None and size != item.size:
            raise RuntimeError(f"Size mismatch: {item.rfilename}")
        with path.open("rb") as handle:
            sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
        if item.lfs and sha256 != item.lfs.sha256:
            raise RuntimeError(f"SHA-256 mismatch: {item.rfilename}")
        files.append({"name": item.rfilename, "size": size, "sha256": sha256})
    manifest = {"repo": REPO, "revision": REVISION, "path": str(DEST), "files": files}
    (ROOT / "model-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Verified {len(files)} files; {sum(f['size'] for f in files):,} bytes", flush=True)


if __name__ == "__main__":
    main()
