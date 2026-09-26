import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Extracted:
    text: str = ""
    metadata: str = ""
    source: str = "none"  # "text" | "ocr" | "listing" | "none"
    sensitive: bool = False


def run(cmd: list[str], timeout: float = 30.0) -> bytes:
    """Run a helper binary; a missing binary, a crash or a timeout all mean 'no output'."""
    if shutil.which(cmd[0]) is None and not Path(cmd[0]).is_file():
        return b""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False).stdout
    except (subprocess.TimeoutExpired, OSError):
        return b""
