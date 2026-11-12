# App de escritorio: imagen pybase (Python + Instant Client + librería btsync + dbus-fast)
# más Qt para dibujar por X11. El contexto de build es la raíz del proyecto.
FROM pybase

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
      libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 \
      libxcb-xinerama0 libdbus-1-3 libfontconfig1 libglib2.0-0 fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "PyQt6>=6.6,<7" "pyqtgraph>=0.13" "pytest-qt>=4.4"

WORKDIR /work
