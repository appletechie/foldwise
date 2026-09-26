"""macOS: Vision OCR in a child process (a hung Vision call can be killed), Spotlight metadata via mdls."""
import json
import plistlib
import sys
from pathlib import Path
from urllib.parse import urlparse

from .base import run


def ocr(path: Path, timeout: float) -> str:
    out = run([sys.executable, "-m", "foldwise.extract.macos", str(path)], timeout)
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        return ""
    labels = data.get("labels", [])
    return ("image labels: " + ", ".join(labels) + "\n" if labels else "") + data.get("text", "")


def metadata(path: Path, timeout: float) -> str:
    out = run(["mdls", "-plist", "-", str(path)], timeout)
    try:
        m = plistlib.loads(out) if out else {}
    except (plistlib.InvalidFileException, ValueError):
        return ""
    parts = []
    hosts = list(dict.fromkeys(urlparse(u).netloc for u in m.get("kMDItemWhereFroms") or [] if "://" in u))
    if hosts:  # hostnames only: download URLs often carry signed tokens
        parts.append("downloaded from " + ", ".join(hosts))
    if "kMDItemPixelWidth" in m:
        parts.append(f"{m['kMDItemPixelWidth']}x{m.get('kMDItemPixelHeight')} px")
    if m.get("kMDItemHasAlphaChannel"):
        parts.append("transparent background")
    if m.get("kMDItemAcquisitionModel"):
        parts.append(f"camera {m.get('kMDItemAcquisitionMake', '')} {m['kMDItemAcquisitionModel']}".replace("  ", " "))
    if m.get("kMDItemCreator"):
        parts.append(f"made with {m['kMDItemCreator']}")
    return " | ".join(parts)


def _vision(path: str) -> dict:
    import Vision
    from Foundation import NSURL

    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
    text_req = Vision.VNRecognizeTextRequest.alloc().init()
    text_req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    label_req = Vision.VNClassifyImageRequest.alloc().init()
    handler.performRequests_error_([text_req, label_req], None)
    lines = []
    for obs in text_req.results() or []:
        candidates = obs.topCandidates_(1)
        if candidates:
            lines.append(str(candidates[0].string()))
    labels = [str(o.identifier()) for o in (label_req.results() or []) if o.confidence() > 0.3][:8]
    return {"text": " ".join(lines), "labels": labels}


if __name__ == "__main__":
    print(json.dumps(_vision(sys.argv[1])))
