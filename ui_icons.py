"""Icon sidebar vector — đổi màu theo theme."""

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_NAV_SVG = {
    "connect": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        '<path d="M12 3v6M8 7l4-4 4 4" stroke="{c}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<rect x="4" y="9" width="16" height="11" rx="2.5" stroke="{c}" stroke-width="2"/>'
        '<path d="M9 14h6" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
        "</svg>"
    ),
    "tools": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        '<rect x="3" y="3" width="8" height="8" rx="2" stroke="{c}" stroke-width="2"/>'
        '<rect x="13" y="3" width="8" height="8" rx="2" stroke="{c}" stroke-width="2"/>'
        '<rect x="3" y="13" width="8" height="8" rx="2" stroke="{c}" stroke-width="2"/>'
        '<rect x="13" y="13" width="8" height="8" rx="2" stroke="{c}" stroke-width="2"/>'
        "</svg>"
    ),
    "settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        '<circle cx="12" cy="12" r="3" stroke="{c}" stroke-width="2"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2'
        'M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="{c}" '
        'stroke-width="2" stroke-linecap="round"/>'
        "</svg>"
    ),
    "about": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">'
        '<circle cx="12" cy="12" r="9" stroke="{c}" stroke-width="2"/>'
        '<path d="M12 10v6M12 7h.01" stroke="{c}" stroke-width="2.5" '
        'stroke-linecap="round"/>'
        "</svg>"
    ),
}


def _hex(color: str) -> str:
    c = (color or "#a1a1aa").strip()
    return c if c.startswith("#") else f"#{c}"


def icon_pixmap(icon_id: str, color: str, size: int = 26) -> QPixmap:
    tpl = _NAV_SVG.get(icon_id, _NAV_SVG["about"])
    svg = tpl.format(c=_hex(color)).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if renderer.isValid():
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
    return pm


def themed_icon(icon_id: str, color: str, size: int = 26) -> QIcon:
    return QIcon(icon_pixmap(icon_id, color, size))


NAV_ICON_IDS = ("connect", "tools", "settings", "about")
