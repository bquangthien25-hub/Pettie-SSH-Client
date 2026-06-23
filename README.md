# 🌌 Pettie SSH Client 🐈

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/UI-PySide6%20%2F%20Qt6-green)](https://wiki.qt.io/Qt_for_Python)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)]()

A Beautiful, Modern & Highly Customizable SSH/SFTP Client for Developers 🐈🐈🐈

🎨 Trải Nghiệm Thao Tác Trực Quan

Dưới đây là một số hình ảnh thực tế từ giao diện Bàn làm việc và các bảng tùy chỉnh sắc nét của ứng dụng:

📝 Thông Tin Dự Án & Tác Giả: 

📌 Chi tiết thông tin

Tên phần mềm Pettie SSH Client

👨‍💻 Nhà phát triển (Developer): ❤️ Cherry🍒 ❤️

Group:  🏝️ OASIS 🏝️ ---- 

Loại hình sản phẩm

ℹ️ Phần mềm mã nguồn mở đa nền tảng (Open-Source Cross-platform)

ℹ️ Phạm vi ứng dụng

👁️‍🗨️ Quản trị hệ thống từ xa, mã hóa tunnel bảo mật, điều khiển hệ thống Native.

✨ Điểm Cốt Lõi & Stack Công Nghệ

🎨 Giao Diện Chính (UI): PySide6 / Qt6 for Python (Độ tùy biến cao, mượt mà)
🔐 Động Cơ Kết Nối: Paramiko SSHv2 Engine (Mã hóa an toàn)
⚙️ Tích Hợp Hệ Thống: Subprocess OS Bridge (Gọi trực tiếp terminal/manager hệ thống)


🔥 Các Tính Năng Đỉnh Cao Trên Bàn Làm Việc

🧠 1. Workspace Quản Trị Trung Tâm

🟢 Terminal Hệ Thống (Native CLI): Nhận diện OS để khởi chạy terminal gốc (cmd/powershell trên Win, gnome-terminal/xterm trên Linux), tự động nhúng phiên bảo mật SSH.

📁 Pettie Transfer (SFTP): Trình quản lý tệp tin hai bảng song song (Dual-pane), trực quan hóa hoàn toàn tiến trình kéo thả tệp từ xa.

🌈 Remote Desktop Bridge: Ánh xạ thông minh luồng đồ họa RDP thông qua SSH tunnel bảo mật, đồng bộ clipboard tức thời.

📊 System Info Monitor: Theo dõi tải lượng phần cứng thời gian thực gồm CPU, RAM, Disk, OS của máy chủ đích.

🔀 Port Forwarding & Host Key Guard: Tunnel cổng trung gian linh hoạt và kiểm soát dấu vân tay khóa bảo mật (SHA256 Fingerprint) chống tấn công nghe lén (MitM).

💅 2. Đỉnh Cao Cá Nhân Hóa UI/UX

🌸 Acrylic Glassmorphism: Hiệu ứng làm mờ kính trong suốt phủ lên các thẻ bo góc cực kỳ dịu mắt.

🌆 Dynamic Backgrounds: Kho hình ảnh anime, thiên nhiên tích hợp sẵn, thay đổi hình nền ứng dụng chỉ với 1 click.

🚀 Chế Độ Mượt (Hardware Acceleration): Tận dụng tối đa render phần cứng của Qt6 giúp giảm giật lag và tối ưu CPU.

🛠️ Hướng Dẫn Cài Đặt & Chạy Từ Source Code 🗨️

1️⃣ Cài đặt môi trường Python

⚠️ NOTE

Khuyến nghị sử dụng Python 3.10 trở lên để đảm bảo tất cả các thư viện đồ họa hiển thị chính xác nhất.

💁‍♂️ Trên Windows 🥝

Tải bản cài đặt mới nhất tại python.org.

Chạy file cài đặt, nhớ tích vào ô [✅] Add Python to PATH trước khi chọn Install.

💁‍♂️ Trên Linux (Ubuntu/Debian/Fedora...):

# Ubuntu / Debian 🍓
sudo apt update && sudo apt install python3 python3-pip python3-venv

# Fedora / RHEL 🍉
sudo dnf install python3 python3-pip

2️⃣ Cài đặt thư viện bổ sung (Dependencies)

📢IMPORTANT 

Các bản phân phối Linux hiện đại thường áp dụng chuẩn PEP 668 để chặn việc cài đặt pip đè lên hệ thống. Hãy chọn cách cài đặt phù hợp bên dưới:

🪟 Trên hệ điều hành Windows:

Mở PowerShell tại thư mục chứa source code và khởi chạy:

pip install -r requirements.txt


🐧 Trên hệ điều hành Linux (Chọn 1 trong 2 cách):

🌟 Cách 1: Sử dụng Môi trường ảo (Venv) — Khuyến nghị (An toàn 100%) 🐊

Tách biệt hoàn toàn thư viện ứng dụng với Python của hệ thống gốc:

# Khởi tạo môi trường ảo "venv"
python3 -m venv venv

# Kích hoạt môi trường ảo
source venv/bin/activate

# Cài đặt từ requirements.txt:
pip install -r requirements.txt


⚡ Cách 2: Cài đặt nhanh bỏ qua cảnh báo — Mì ăn liền (Tiện lợi) 🐊

Dành cho người muốn cài trực tiếp vào hệ thống toàn cục:

pip3 install -r requirements.txt --break-system-packages


[⚠️CAUTION]

⚠️ Cảnh báo rủi ro: Phương pháp này sẽ cài đè thư viện trực tiếp vào môi trường Python mặc định của hệ điều hành. Có thể gây xung đột không mong muốn cho các công cụ chạy bằng Python khác của Linux.

3️⃣ Kích hoạt ứng dụng

Di chuyển Terminal/CMD vào thư mục chứa dự án và kích hoạt:

python main_gui.py


(Trên Linux bạn có thể cần chạy bằng lệnh python3 main_gui.py)

📦 Hướng Dẫn Đóng Gói Thành File Thực Thi (.exe/.bin)

Nếu muốn đóng gói toàn bộ dự án thành một file chạy độc lập duy nhất để gửi cho bạn bè hoặc người dùng cuối không cài sẵn Python, hãy sử dụng PyInstaller:

Cài đặt PyInstaller:

pip install pyinstaller


Khởi chạy biên dịch tối ưu (ẩn cửa sổ CMD đen, nén 1 file):

pyinstaller --noconsole --onefile main_gui.py


Nhận sản phẩm: File chạy độc lập nằm ngay trong thư mục dist/ mới được tạo ra!

**Lưu ý:** Nên dùng `main_gui.spec` (đã gói thư mục `assets`) thay vì lệnh `--onefile` thuần ở trên.

🤝 Đóng Góp Dự Án

🗨️ Mọi ý kiến đóng góp, báo lỗi (Issues) hoặc gửi yêu cầu tính năng mới (Pull Requests) đều được chào đón tại:
🔗 Pettie-SSH-Client GitHub Repository
