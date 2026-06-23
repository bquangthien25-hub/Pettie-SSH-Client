"""Kiểu đồ họa giao diện — classic, liquid glass, neon, minimal, aurora."""

VISUAL_STYLE_IDS = [
    ("classic", "Classic — chuẩn, rõ ràng"),
    ("glass", "Liquid Glass — kính mờ, viền sáng"),
    ("neon", "Neon Cyber — viền phát sáng"),
    ("minimal", "Minimal — phẳng, tối giản"),
    ("aurora", "Aurora — gradient nhẹ"),
    ("frosted", "Frosted — panel sương mờ"),
]


def resolve_visual_tokens(style_id, mode, palette, transparent=False):
    """
    Trả về dict token ghi đè lên màu nền/viền của build_stylesheet.
    """
    acc = palette["accent"]
    acc2 = palette["accent2"]
    nav_sel = palette["nav_sel"]
    style_id = (style_id or "classic").lower()

    if mode == "light":
        base = {
            "text": "#0f172a",
            "muted": "#64748b",
            "field": "#475569",
            "card": "rgba(255, 255, 255, 0.88)",
            "card_border": "rgba(148, 163, 184, 0.55)",
            "nav_bg": "rgba(255, 255, 255, 0.92)",
            "input_bg": "#ffffff",
            "input_border": "#cbd5e1",
            "tool_bg": "rgba(248, 250, 252, 0.92)",
            "tool_hover_bg": "rgba(255, 255, 255, 0.95)",
            "tool_hover_text": acc2,
            "log_bg": "rgba(255, 255, 255, 0.9)",
            "nav_text": "#64748b",
            "nav_hover": "#f1f5f9",
            "nav_checked_bg": nav_sel,
            "nav_checked_text": acc2,
            "nav_border_w": 3,
            "card_radius": 20,
            "nav_radius": 12,
            "overlay": 0.62,
            "glass_highlight": "rgba(255,255,255,0.0)",
        }
    else:
        base = {
            "text": "#fafafa",
            "muted": "#a1a1aa",
            "field": "#d4d4d8",
            "card": "rgba(24, 24, 27, 0.82)",
            "card_border": "rgba(63, 63, 70, 0.7)",
            "nav_bg": "rgba(24, 24, 27, 0.88)",
            "input_bg": "#18181b",
            "input_border": "#3f3f46",
            "tool_bg": "rgba(39, 39, 42, 0.85)",
            "tool_hover_bg": "rgba(22, 22, 30, 0.92)",
            "tool_hover_text": acc,
            "log_bg": "rgba(24, 24, 27, 0.88)",
            "nav_text": "#71717a",
            "nav_hover": "#27272a",
            "nav_checked_bg": nav_sel,
            "nav_checked_text": acc,
            "nav_border_w": 3,
            "card_radius": 20,
            "nav_radius": 12,
            "overlay": 0.45,
            "glass_highlight": "rgba(255,255,255,0.0)",
        }

    if transparent:
        if mode == "light":
            base.update({
                "card": "rgba(255, 255, 255, 0.42)",
                "nav_bg": "rgba(255, 255, 255, 0.38)",
                "input_bg": "rgba(255, 255, 255, 0.55)",
                "tool_bg": "rgba(255, 255, 255, 0.45)",
                "tool_hover_bg": "rgba(255, 255, 255, 0.62)",
                "log_bg": "rgba(255, 255, 255, 0.48)",
                "card_border": "rgba(255, 255, 255, 0.55)",
                "overlay": 0.08,
            })
        else:
            base.update({
                "card": "rgba(9, 9, 11, 0.40)",
                "nav_bg": "rgba(9, 9, 11, 0.32)",
                "input_bg": "rgba(9, 9, 11, 0.52)",
                "tool_bg": "rgba(9, 9, 11, 0.42)",
                "tool_hover_bg": "rgba(9, 9, 11, 0.58)",
                "log_bg": "rgba(9, 9, 11, 0.48)",
                "card_border": "rgba(255, 255, 255, 0.18)",
                "overlay": 0.12,
            })

    if style_id == "glass":
        if mode == "light":
            base.update({
                "card": "rgba(255, 255, 255, 0.28)",
                "nav_bg": "rgba(255, 255, 255, 0.22)",
                "input_bg": "rgba(255, 255, 255, 0.38)",
                "tool_bg": "rgba(255, 255, 255, 0.26)",
                "tool_hover_bg": "rgba(255, 255, 255, 0.42)",
                "log_bg": "rgba(255, 255, 255, 0.30)",
                "card_border": "rgba(255, 255, 255, 0.65)",
                "nav_hover": "rgba(255, 255, 255, 0.35)",
                "nav_checked_bg": f"rgba({ _hex_rgb(acc) }, 0.22)",
                "glass_highlight": "rgba(255,255,255,0.45)",
                "card_radius": 22,
                "overlay": min(base["overlay"], 0.06),
            })
        else:
            base.update({
                "card": "rgba(18, 18, 24, 0.38)",
                "nav_bg": "rgba(12, 12, 18, 0.42)",
                "input_bg": "rgba(12, 12, 18, 0.55)",
                "tool_bg": "rgba(18, 18, 26, 0.40)",
                "tool_hover_bg": "rgba(24, 24, 32, 0.55)",
                "log_bg": "rgba(12, 12, 18, 0.45)",
                "card_border": "rgba(255, 255, 255, 0.22)",
                "nav_hover": "rgba(255, 255, 255, 0.08)",
                "nav_checked_bg": f"rgba({ _hex_rgb(acc) }, 0.28)",
                "glass_highlight": "rgba(255,255,255,0.12)",
                "card_radius": 22,
                "overlay": min(base["overlay"], 0.10),
            })

    elif style_id == "neon":
        glow = f"rgba({ _hex_rgb(acc) }, 0.45)"
        if mode == "light":
            base.update({
                "card": "rgba(255, 255, 255, 0.75)",
                "card_border": glow,
                "nav_bg": "rgba(15, 23, 42, 0.06)",
                "nav_checked_bg": f"rgba({ _hex_rgb(acc) }, 0.15)",
                "nav_checked_text": acc2,
                "tool_bg": "rgba(255,255,255,0.7)",
                "tool_hover_bg": f"rgba({ _hex_rgb(acc) }, 0.12)",
                "input_border": glow,
            })
        else:
            base.update({
                "card": "rgba(9, 9, 14, 0.72)",
                "card_border": glow,
                "nav_bg": "rgba(6, 6, 12, 0.85)",
                "nav_checked_bg": f"rgba({ _hex_rgb(acc) }, 0.22)",
                "tool_bg": "rgba(12, 12, 20, 0.75)",
                "tool_hover_bg": f"rgba({ _hex_rgb(acc) }, 0.18)",
                "input_border": f"rgba({ _hex_rgb(acc) }, 0.55)",
                "overlay": min(base["overlay"] + 0.05, 0.55),
            })

    elif style_id == "minimal":
        if mode == "light":
            base.update({
                "card": "rgba(255, 255, 255, 0.96)",
                "card_border": "rgba(226, 232, 240, 0.9)",
                "nav_bg": "rgba(248, 250, 252, 0.98)",
                "tool_bg": "rgba(248, 250, 252, 0.95)",
                "nav_border_w": 2,
                "card_radius": 14,
                "nav_radius": 10,
            })
        else:
            base.update({
                "card": "rgba(18, 18, 20, 0.95)",
                "card_border": "rgba(39, 39, 42, 0.5)",
                "nav_bg": "rgba(12, 12, 14, 0.98)",
                "tool_bg": "rgba(24, 24, 27, 0.9)",
                "nav_border_w": 2,
                "card_radius": 14,
                "nav_radius": 10,
            })

    elif style_id == "aurora":
        if mode == "light":
            base.update({
                "nav_checked_bg": f"qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 rgba({_hex_rgb(acc)},0.2), stop:1 rgba({_hex_rgb(acc2)},0.15))",
                "tool_hover_bg": f"rgba({ _hex_rgb(acc) }, 0.10)",
                "card_border": f"rgba({ _hex_rgb(acc) }, 0.35)",
            })
        else:
            base.update({
                "nav_checked_bg": f"qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 rgba({_hex_rgb(acc)},0.35), stop:1 rgba({_hex_rgb(acc2)},0.2))",
                "tool_hover_bg": f"rgba({ _hex_rgb(acc) }, 0.15)",
                "card_border": f"rgba({ _hex_rgb(acc) }, 0.4)",
            })

    elif style_id == "frosted":
        if mode == "light":
            base.update({
                "card": "rgba(255, 255, 255, 0.55)",
                "nav_bg": "rgba(255, 255, 255, 0.48)",
                "input_bg": "rgba(255, 255, 255, 0.65)",
                "tool_bg": "rgba(255, 255, 255, 0.50)",
                "card_border": "rgba(255, 255, 255, 0.75)",
                "overlay": min(base["overlay"], 0.15),
            })
        else:
            base.update({
                "card": "rgba(30, 30, 38, 0.50)",
                "nav_bg": "rgba(20, 20, 28, 0.55)",
                "input_bg": "rgba(24, 24, 30, 0.62)",
                "tool_bg": "rgba(28, 28, 36, 0.48)",
                "card_border": "rgba(255, 255, 255, 0.16)",
                "overlay": min(base["overlay"], 0.18),
            })

    return base


def _hex_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 6:
        return f"{int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)}"
    return "45,212,191"
