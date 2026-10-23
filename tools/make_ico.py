"""앱 아이콘 SVG -> exe / 설치본용 .ico 변환 (아이콘을 바꿨을 때만 1회 실행)

    python tools/make_ico.py

각 크기를 PNG 로 렌더링해 ICO 컨테이너에 담는다 (Windows Vista 이상은 PNG 항목을 지원).
"""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ico", "taskpin_icon_A_memo.svg")
DST = os.path.join(ROOT, "ico", "taskpin.ico")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()

    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(data)


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 - QImage/QPainter 에 필요
    renderer = QSvgRenderer(SRC)
    if not renderer.isValid():
        sys.exit(f"SVG 를 읽지 못했습니다: {SRC}")

    images = [(size, render_png(renderer, size)) for size in SIZES]

    # ICONDIR + ICONDIRENTRY * n + 이미지 데이터
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size  # 256 은 0 으로 기록
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)

    with open(DST, "wb") as f:
        f.write(header + entries + blobs)
    print(f"{DST} ({', '.join(str(s) for s in SIZES)}px)")


if __name__ == "__main__":
    main()
