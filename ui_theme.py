"""Đường dẫn assets & danh sách nền có sẵn."""

import sys
import os


def get_resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


ASSETS_DIR = get_resource_path("assets")
APP_LOGO = get_resource_path("assets/app_logo.png")
OASIS_LOGO = get_resource_path("assets/oasis_logo.png")
BG_ANIME = get_resource_path("assets/bg_anime.png")

BACKGROUND_PRESETS = [
    {"id": "sakura_sky", "name": "Sakura Sky", "file": "bg_sakura_sky.png"},
    {"id": "sunset_beach", "name": "Sunset Beach", "file": "bg_sunset_beach.png"},
    {"id": "aurora", "name": "Aurora", "file": "bg_aurora.png"},
    {"id": "cloud_city", "name": "Cloud City", "file": "bg_cloud_city.png"},
    {"id": "lavender", "name": "Lavender", "file": "bg_lavender.png"},
    {"id": "morning", "name": "Morning Light", "file": "bg_morning.png"},
    {"id": "ocean_day", "name": "Ocean Day", "file": "bg_ocean_day.png"},
    {"id": "classic_dark", "name": "Cyber Night", "file": "bg_anime.png", "in_root": True},
]


def preset_path(preset):
    if preset.get("in_root"):
        return get_resource_path(f"assets/{preset['file']}")
    return get_resource_path(f"assets/backgrounds/{preset['file']}")


def resolve_background(bg_id):
    for p in BACKGROUND_PRESETS:
        if p["id"] == bg_id:
            path = preset_path(p)
            if os.path.isfile(path):
                return path
    if os.path.isfile(BG_ANIME):
        return BG_ANIME
    return None


def list_available_backgrounds():
    out = []
    for p in BACKGROUND_PRESETS:
        path = preset_path(p)
        if os.path.isfile(path):
            out.append({**p, "path": path})
    return out
