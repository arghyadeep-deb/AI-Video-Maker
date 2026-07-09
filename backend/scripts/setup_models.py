"""Downloads model weights into the vendored checkouts (Wav2Lip, OpenVoice).

Idempotent: skips any file that already exists at its expected size. Run
from the backend/ directory: `python scripts/setup_models.py`.

Sources (recorded here since Wav2Lip's own README points at Google Drive,
which throttles/blocks non-interactive downloads):
- wav2lip_gan.pth: mirrored on Hugging Face (camenduru/Wav2Lip), sha256
  ca9ab7b7b812c0e80a6e70a5977c545a1e8a365a6c49d5e533023c034d7ac3d8 -
  matches the hash independently referenced across other public mirrors
  of the same file (checked at task-11 time), which is the closest thing
  to provenance verification available for a research-code checkpoint
  that was never published with an official checksum.
- s3fd.pth: the official face-detection weight URL linked directly from
  Wav2Lip's own README, sha256
  619a31681264d3f7f7fc7a16a42cbbe8b23f31a256f75a366e5a1bcd59b33543 - note
  the filename itself embeds this hash's prefix (s3fd-619a316812.pth),
  which is the upstream project's own self-consistency convention.

task-18 additions (OpenVoice V2 tone-color converter - the ONLY piece of
OpenVoice this project uses; edge-tts is the base-speech generator per
specs/01-requirements/11-personal-voice.md, so the `base_speakers/*.pth`
files in the same HF repo aren't needed and aren't downloaded here):
- converter/checkpoint.pth: official myshell-ai/OpenVoiceV2 Hugging Face
  repo (the upstream README's own S3 mirror link,
  myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip,
  is dead - "NoSuchBucket" - confirmed by actually requesting it, not
  assumed). sha256
  9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "wav2lip"
OPENVOICE_DIR = Path(__file__).resolve().parent.parent / "vendor" / "openvoice"

DOWNLOADS = [
    {
        "url": "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth",
        "dest": VENDOR_DIR / "checkpoints" / "wav2lip_gan.pth",
        "size": 435801865,
        "sha256": "ca9ab7b7b812c0e80a6e70a5977c545a1e8a365a6c49d5e533023c034d7ac3d8",
    },
    {
        "url": "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth",
        "dest": VENDOR_DIR / "face_detection" / "detection" / "sfd" / "s3fd.pth",
        "size": 89843225,
        "sha256": "619a31681264d3f7f7fc7a16a42cbbe8b23f31a256f75a366e5a1bcd59b33543",
    },
    {
        "url": "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/checkpoint.pth",
        "dest": OPENVOICE_DIR / "checkpoints_v2" / "converter" / "checkpoint.pth",
        "size": 131320490,
        "sha256": "9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e",
    },
    {
        "url": "https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter/config.json",
        "dest": OPENVOICE_DIR / "checkpoints_v2" / "converter" / "config.json",
        "size": 838,
        "sha256": None,  # small config file - size check alone is enough, no need to pin a hash
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    for item in DOWNLOADS:
        dest: Path = item["dest"]
        if dest.exists() and dest.stat().st_size == item["size"]:
            print(f"[skip] {dest} already present ({item['size']} bytes)")
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[download] {item['url']} -> {dest}")
        urllib.request.urlretrieve(item["url"], dest)

        actual_size = dest.stat().st_size
        actual_sha256 = _sha256(dest) if item["sha256"] is not None else None
        if actual_size != item["size"] or (item["sha256"] is not None and actual_sha256 != item["sha256"]):
            dest.unlink(missing_ok=True)
            print(
                f"[FAIL] {dest}: expected size={item['size']} sha256={item['sha256']}, "
                f"got size={actual_size} sha256={actual_sha256}. Deleted the partial/wrong file.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[ok] {dest} verified ({actual_size} bytes)")


if __name__ == "__main__":
    main()
