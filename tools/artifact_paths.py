"""为离线验证产物提供独立于发布包的输出目录。"""

from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parents[1] / ".artifacts" / "validation"


def artifact_path(name):
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    return VALIDATION_DIR / name
