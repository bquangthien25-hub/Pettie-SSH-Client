"""7 theme màu × chế độ sáng/tối × kiểu đồ họa."""

from visual_styles import resolve_visual_tokens

THEME_IDS = [
    ("teal", "Teal Cyber"),
    ("violet", "Violet Dream"),
    ("rose", "Rose Sunset"),
    ("amber", "Amber Gold"),
    ("ocean", "Ocean Blue"),
    ("forest", "Forest Mint"),
    ("sakura", "Sakura Pink"),
]

PALETTES = {
    "teal": {"accent": "#2dd4bf", "accent2": "#14b8a6", "nav_sel": "#164e63"},
    "violet": {"accent": "#a78bfa", "accent2": "#8b5cf6", "nav_sel": "#4c1d95"},
    "rose": {"accent": "#fb7185", "accent2": "#f43f5e", "nav_sel": "#881337"},
    "amber": {"accent": "#fbbf24", "accent2": "#f59e0b", "nav_sel": "#78350f"},
    "ocean": {"accent": "#38bdf8", "accent2": "#0ea5e9", "nav_sel": "#0c4a6e"},
    "forest": {"accent": "#4ade80", "accent2": "#22c55e", "nav_sel": "#14532d"},
    "sakura": {"accent": "#f9a8d4", "accent2": "#ec4899", "nav_sel": "#831843"},
}


def build_stylesheet(
    theme_id="teal",
    mode="dark",
    overlay=0.62,
    transparent=False,
    visual_style="classic",
):
    p = PALETTES.get(theme_id, PALETTES["teal"])
    acc = p["accent"]
    acc2 = p["accent2"]
    nav = p["nav_sel"]

    link = "#2563eb" if mode == "light" else acc

    t = resolve_visual_tokens(visual_style, mode, p, transparent=transparent)
    text = t["text"]
    muted = t["muted"]
    field = t["field"]
    card = t["card"]
    card_border = t["card_border"]
    nav_bg = t["nav_bg"]
    input_bg = t["input_bg"]
    input_border = t["input_border"]
    tool_bg = t["tool_bg"]
    tool_hover_bg = t["tool_hover_bg"]
    tool_hover_text = t["tool_hover_text"]
    log_bg = t["log_bg"]
    nav_text = t["nav_text"]
    nav_hover = t["nav_hover"]
    nav_checked_bg = t["nav_checked_bg"]
    nav_checked_text = t["nav_checked_text"]
    nav_border_w = t["nav_border_w"]
    card_radius = t["card_radius"]
    nav_radius = t["nav_radius"]
    glass_hi = t.get("glass_highlight", "transparent")

    if mode == "light":
        popup_bg = "#ffffff"
        popup_sel_bg = "#e2e8f0"
        popup_sel_text = "#0f172a"
    else:
        popup_bg = "#27272a"
        popup_sel_bg = nav
        popup_sel_text = acc

    overlay_use = overlay
    if transparent or visual_style in ("glass", "frosted"):
        overlay_use = t.get("overlay", overlay)
    elif mode == "light":
        overlay_use = min(overlay + 0.18, 0.82)

    return f"""
        QWidget#mainRoot {{ background: transparent; color: {text};
            font-family: 'Segoe UI', Inter, sans-serif; font-size: 13px; }}
        QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QFrame#navRail {{
            background-color: {nav_bg};
            border-right: 1px solid {card_border};
        }}
        QLabel#brandName {{ color: {text}; font-size: 15px; font-weight: 700; }}
        QLabel#brandVer {{ color: {muted}; font-size: 10px; }}
        QToolButton#navBtn, QPushButton#navBtn {{
            background: transparent; color: {nav_text}; border: none;
            border-radius: {nav_radius}px; padding: 10px 6px; font-size: 11px; font-weight: 600;
        }}
        QToolButton#navBtn:hover, QPushButton#navBtn:hover {{
            background-color: {nav_hover}; color: {text};
        }}
        QToolButton#navBtn:checked, QPushButton#navBtn:checked {{
            background-color: {nav_checked_bg}; color: {nav_checked_text};
            border-left: {nav_border_w}px solid {acc};
            border-top: 1px solid {glass_hi};
        }}
        QFrame#contentCard {{
            background-color: {card}; border: 1px solid {card_border};
            border-radius: {card_radius}px;
        }}
        QLabel#cardTitle {{ font-size: 22px; font-weight: 700; color: {text}; }}
        QLabel#cardDesc {{ color: {muted}; font-size: 13px; }}
        QLabel#fieldLabel {{ color: {field}; font-size: 12px; font-weight: 600; }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {input_bg}; color: {text};
            border: 1px solid {input_border}; border-radius: 10px; padding: 10px 14px;
        }}
        QLineEdit:focus, QComboBox:focus {{ border-color: {acc}; }}
        QComboBox::drop-down {{
            border: none; width: 28px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {muted};
            margin-right: 10px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {popup_bg};
            color: {text};
            border: 1px solid {input_border};
            border-radius: 8px;
            padding: 4px;
            outline: none;
            selection-background-color: {popup_sel_bg};
            selection-color: {popup_sel_text};
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 28px;
            padding: 4px 12px;
            color: {text};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {popup_sel_bg};
            color: {popup_sel_text};
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {popup_sel_bg};
            color: {popup_sel_text};
        }}
        QCheckBox {{ color: {muted}; spacing: 8px; }}
        QListWidget {{
            background-color: {input_bg}; color: {text};
            border: 1px solid {input_border}; border-radius: 10px;
        }}
        QListWidget::item {{
            color: {text};
            padding: 6px 8px;
        }}
        QListWidget::item:selected {{
            background-color: {popup_sel_bg};
            color: {popup_sel_text};
        }}
        QListWidget::item:hover {{
            background-color: {popup_sel_bg};
            color: {popup_sel_text};
        }}
        QPushButton#toolCard {{
            background-color: {tool_bg}; border: 1px solid {card_border};
            border-radius: {card_radius}px; padding: 24px; font-size: 14px;
            font-weight: 700; color: {text}; text-align: left;
        }}
        QPushButton#toolCard:hover {{
            border-color: {acc}; background-color: {tool_hover_bg}; color: {tool_hover_text};
        }}
        QPushButton#toolCard:disabled {{
            background-color: {card}; color: {muted}; border-color: {card_border};
        }}
        QLabel#settingsSection {{ color: {acc}; font-weight: 700; margin-top: 8px; }}
        QPushButton#bgThumb {{
            border: 2px solid transparent; border-radius: 12px; padding: 0;
        }}
        QPushButton#bgThumb:checked {{ border-color: {acc}; }}
        QFrame#aboutBitvisePanel {{
            background-color: {card};
            border: 1px solid {card_border};
            border-radius: 4px;
        }}
        QGroupBox#aboutGroup {{
            color: {text};
            font-size: 13px;
            font-weight: 700;
            border: 1px solid {card_border};
            border-radius: 3px;
            margin-top: 10px;
            padding: 4px 0 0 0;
            background-color: {input_bg};
        }}
        QGroupBox#aboutGroup::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 0px;
            padding: 0 4px;
            color: {text};
            background-color: {input_bg};
        }}
        QLabel#aboutHeadline {{
            font-size: 14px;
            font-weight: 700;
            color: {text};
            padding: 0;
            margin: 0;
        }}
        QLabel#aboutBody {{
            font-size: 13px;
            color: {text};
            padding: 0;
            margin: 0;
        }}
        QLabel#aboutLink {{
            font-size: 13px;
            color: {link};
        }}
        QLabel#aboutLink a, QLabel#aboutBody a {{
            color: {link};
            text-decoration: none;
        }}
        QLabel#aboutOasisLogo {{
            background: transparent;
            border: none;
            padding: 4px 0;
        }}
    """, overlay_use


def combo_popup_stylesheet(theme_id="teal", mode="dark"):
    """Style riêng cho QListView popup của QComboBox (Windows cần set trực tiếp)."""
    p = PALETTES.get(theme_id, PALETTES["teal"])
    if mode == "light":
        return """
            QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                outline: none;
                selection-background-color: #e2e8f0;
                selection-color: #0f172a;
            }
            QAbstractItemView::item {
                min-height: 28px;
                padding: 4px 12px;
                color: #0f172a;
            }
            QAbstractItemView::item:selected,
            QAbstractItemView::item:hover {
                background-color: #e2e8f0;
                color: #0f172a;
            }
        """
    nav = p["nav_sel"]
    acc = p["accent"]
    return f"""
        QAbstractItemView {{
            background-color: #27272a;
            color: #fafafa;
            border: 1px solid #3f3f46;
            outline: none;
            selection-background-color: {nav};
            selection-color: {acc};
        }}
        QAbstractItemView::item {{
            min-height: 28px;
            padding: 4px 12px;
            color: #fafafa;
        }}
        QAbstractItemView::item:selected,
        QAbstractItemView::item:hover {{
            background-color: {nav};
            color: {acc};
        }}
    """


def login_button_style(mode, accent, accent2):
    if mode == "light":
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {accent}, stop:1 {accent2});
                color: #0f172a; font-weight: 700; border: none;
                border-radius: 12px; padding: 12px 32px; font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {accent2}; color: white; }}
        """
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {accent2}, stop:1 {accent});
            color: white; font-weight: 700; border: none;
            border-radius: 12px; padding: 12px 32px; font-size: 14px;
        }}
        QPushButton:hover {{ background-color: {accent}; }}
    """
