#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Pettie SSH Client — Linux: MỘT LỆNH CÀI TẤT CẢ
#  bash install-linux.sh
#
#  Remote Desktop: Remmina engine (ổn định) + xfreerdp dự phòng
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Script này chỉ dùng trên Linux."
  exit 1
fi

bundle_freerdp() {
  local OUT="$ROOT/vendor/freerdp"
  local TMP
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' RETURN

  rm -rf "$OUT"
  mkdir -p "$OUT/bin" "$OUT/lib"

  copy_libs() {
    local dir="$1"
    shopt -s nullglob
    for so in "$dir"/libfreerdp*.so* "$dir"/libwinpr*.so*; do
      cp -a "$so" "$OUT/lib/" 2>/dev/null || true
    done
  }

  if command -v apt-get >/dev/null 2>&1; then
    cd "$TMP"
    apt-get download freerdp2-x11 libfreerdp2-2 libwinpr2-2 2>/dev/null \
      || apt-get download freerdp2-x11
    mkdir -p extract
    for deb in *.deb; do dpkg-deb -x "$deb" extract/; done
    shopt -s nullglob
    for bin in extract/usr/bin/xfreerdp extract/usr/bin/xfreerdp3 extract/usr/bin/wlfreerdp; do
      [[ -f "$bin" ]] && cp -a "$bin" "$OUT/bin/"
    done
    for libdir in extract/usr/lib/x86_64-linux-gnu extract/usr/lib64 extract/usr/lib; do
      [[ -d "$libdir" ]] && copy_libs "$libdir"
    done
  elif command -v dnf >/dev/null 2>&1; then
    cd "$TMP"
    dnf download -y freerdp 2>/dev/null || dnf download freerdp
    mkdir -p extract
    for rpm in *.rpm; do
      rpm2cpio "$rpm" | (cd extract && cpio -idmv >/dev/null 2>&1)
    done
    for bin in extract/usr/bin/xfreerdp extract/usr/bin/xfreerdp3; do
      [[ -f "$bin" ]] && cp -a "$bin" "$OUT/bin/"
    done
    for libdir in extract/usr/lib64 extract/usr/lib; do
      [[ -d "$libdir" ]] && copy_libs "$libdir"
    done
  elif command -v pacman >/dev/null 2>&1; then
    cd "$TMP"
    pacman -Sw --noconfirm freerdp2 2>/dev/null || true
    mkdir -p extract
    for pkg in freerdp2-*.pkg.tar.*; do
      [[ -f "$pkg" ]] || continue
      tar -xf "$pkg" -C extract/ 2>/dev/null || true
    done
    for bin in extract/usr/bin/xfreerdp extract/usr/bin/xfreerdp3; do
      [[ -f "$bin" ]] && cp -a "$bin" "$OUT/bin/"
    done
    [[ -d extract/usr/lib ]] && copy_libs extract/usr/lib
  else
    return 0
  fi

  cd "$ROOT"
  chmod +x "$OUT/bin/"* 2>/dev/null || true
  [[ -f "$OUT/bin/xfreerdp" || -f "$OUT/bin/xfreerdp3" ]]
}

rdp_client_hint() {
  if command -v remmina >/dev/null 2>&1; then
    echo "remmina: $(command -v remmina)"
  elif command -v flatpak >/dev/null 2>&1 && flatpak info org.remmina.Remmina &>/dev/null; then
    echo "remmina: flatpak org.remmina.Remmina"
  else
    echo "remmina: chưa cài"
  fi
  echo "  xfreerdp: $(command -v xfreerdp 2>/dev/null || echo 'vendor/freerdp/bin (dự phòng)')"
}

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     Pettie SSH Client — Cài đặt Linux (1 lệnh)   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

echo "==> [1/5] Cài Python + Remmina (Remote Desktop) + xfreerdp dự phòng..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    remmina remmina-plugin-rdp \
    freerdp2-x11 libfreerdp2-2 libwinpr2-2 dpkg-dev \
    || sudo apt-get install -y \
      python3 python3-venv python3-pip \
      remmina remmina-plugin-rdp freerdp2-x11
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip remmina freerdp rpm-build
elif command -v pacman >/dev/null 2>&1; then
  sudo pacman -S --noconfirm python python-pip remmina freerdp2 base-devel
elif command -v zypper >/dev/null 2>&1; then
  sudo zypper install -y python3 python3-pip remmina freerdp
fi

echo "==> [2/5] pip install -r requirements.txt ..."
[[ -d venv ]] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt

echo "==> [3/5] Đóng gói xfreerdp dự phòng vào vendor/freerdp/ (khi không có Remmina)..."
if bundle_freerdp; then
  echo "    OK: vendor/freerdp/bin (dự phòng)"
else
  echo "    Bỏ qua — dùng Remmina/xfreerdp hệ thống"
fi

echo "==> [4/5] PyInstaller → dist/main_gui ..."
cd "$ROOT"
pyinstaller --noconfirm --clean main_gui.spec

echo "==> [5/5] Tạo lệnh ./pettie và shortcut menu..."
cat > "$ROOT/pettie" <<'LAUNCH'
#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ -x "$ROOT/dist/main_gui" ]]; then exec "$ROOT/dist/main_gui" "$@"; fi
if [[ -f "$ROOT/venv/bin/python3" ]]; then exec "$ROOT/venv/bin/python3" "$ROOT/main_gui.py" "$@"; fi
exec python3 "$ROOT/main_gui.py" "$@"
LAUNCH
chmod +x "$ROOT/pettie"

DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DESKTOP_DIR"
ICON="$ROOT/assets/logo.png"
[[ -f "$ICON" ]] || ICON="utilities-terminal"
cat > "$DESKTOP_DIR/pettie-ssh-client.desktop" <<EOF
[Desktop Entry]
Name=Pettie SSH Client
Comment=SSH, SFTP & Remote Desktop
Exec=$ROOT/pettie
Icon=$ICON
Path=$ROOT
Terminal=false
Type=Application
Categories=Network;RemoteAccess;
StartupWMClass=main_gui
EOF

echo ""
echo "✓ Xong! Chạy: ./pettie  hoặc  ./dist/main_gui"
echo "  Remote Desktop:"
rdp_client_hint | sed 's/^/    /'
