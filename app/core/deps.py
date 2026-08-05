"""Runtime dependency verification for core (non-AI) packages."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PackageRequirement:
    module_name: str
    pip_name: str
    required_for: str


CORE_REQUIREMENTS: tuple[PackageRequirement, ...] = (
    PackageRequirement("PySide6", "PySide6", "GUI"),
    PackageRequirement("yt_dlp", "yt-dlp", "video downloads"),
    PackageRequirement("requests", "requests", "thumbnail fetching"),
    PackageRequirement("PIL", "Pillow", "image processing"),
    PackageRequirement("certifi", "certifi", "HTTPS certificate verification"),
    PackageRequirement("truststore", "truststore", "Windows system HTTPS certificates"),
)


def check_package(requirement: PackageRequirement) -> bool:
    try:
        importlib.import_module(requirement.module_name)
        return True
    except ImportError:
        return False


def get_missing_core_packages() -> list[PackageRequirement]:
    return [req for req in CORE_REQUIREMENTS if not check_package(req)]


def format_install_instructions(missing: list[PackageRequirement]) -> str:
    if not missing:
        return ""

    pip_cmd = f'"{sys.executable}" -m pip install -r requirements.txt'
    lines = [
        "Some required packages are missing:",
        "",
    ]
    for req in missing:
        lines.append(f"  • {req.pip_name} ({req.required_for})")
    lines.extend(
        [
            "",
            "Install all dependencies with:",
            pip_cmd,
        ]
    )
    return "\n".join(lines)
