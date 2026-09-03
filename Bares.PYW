import sys
import subprocess
import importlib.util
import ctypes
import threading
import time
import webbrowser

# --------------------------
# Önce kütüphane yükleme kısmı
# --------------------------
def install_if_missing(package_name, module_name=None):
    module_name = module_name or package_name
    if importlib.util.find_spec(module_name) is None:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        except Exception as e:
            print(f"{package_name} yüklenemedi: {e}")
            sys.exit(1)

for lib in [("pyqt5", None), ("pywin32", None), ("psutil", None)]:
    install_if_missing(*lib)

# --------------------------
# Kütüphaneler yüklenince import ediliyor
# --------------------------
import win32gui
import win32process
import win32api
import win32con
import psutil
from ctypes import wintypes
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QMenu, QMessageBox
)
from PyQt5.QtCore import QTimer, QTime, Qt, QPropertyAnimation, QRect
from PyQt5.QtGui import QFont

# Roket modu için pencere değişimi olayları / Foreground window change event constants
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000

# Öncelik değişimine dokunulmayacak sistem/kabuk süreçleri / System-shell processes to skip
ROCKET_EXCLUDED_PROCESSES = {
    "explorer.exe",
    "searchhost.exe",
    "searchapp.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "applicationframehost.exe",
    "systemsettings.exe",
    "lockapp.exe",
    "dwm.exe",
    "sihost.exe",
}

# Roket modu için WinEvent callback tipi ve doğru handle boyutlu (64-bit uyumlu) imzalar
WinEventProcType = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD
)
ctypes.windll.user32.SetWinEventHook.restype = wintypes.HANDLE
ctypes.windll.user32.SetWinEventHook.argtypes = [
    wintypes.UINT, wintypes.UINT, wintypes.HMODULE, WinEventProcType,
    wintypes.DWORD, wintypes.DWORD, wintypes.UINT
]
ctypes.windll.user32.UnhookWinEvent.restype = wintypes.BOOL
ctypes.windll.user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

# --------------------------
# Admin kontrolü
# --------------------------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

app = QApplication(sys.argv)

if not is_admin():
    QMessageBox.warning(None, "Yönetici Gerekiyor / Administrator Required",
                        "Roket modunun çalışması için yönetici olarak çalıştırınız. / Please run as administrator to activate rocket mode.")

# Konsolu gizle
try:
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd != 0:
        ctypes.windll.user32.ShowWindow(whnd, 0)
except Exception as e:
    print(f"Konsol gizleme hatası: {e}")

# --------------------------
# Kenar butonu
# --------------------------
class EdgeButton(QWidget):
    def __init__(self, callback):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(40, 50)
        self.setStyleSheet("background-color: #444; border-radius: 0px;")
        self.callback = callback

        self.button = QPushButton("▶", self)
        self.button.setGeometry(0, 0, 40, 50)
        self.button.setStyleSheet("background-color: #444; color: white; border: none; font-size: 16px;")
        self.button.clicked.connect(self.restore_bar)
        self.move(0, 700)

    def restore_bar(self):
        self.hide()
        self.callback()

# --------------------------
# Roket Görev Çubuğu
# --------------------------
class RocketTaskbar(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Görev Çubuğu / Taskbar")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedHeight(50)
        self.setStyleSheet("background-color: #2d2d30; color: white;")

        self.old_pos = self.pos()
        self.selected_engine = "DuckDuckGo"
        self.rocket_mode_running = False
        self.rocket_thread = None
        self.rocket_thread_id = None
        self.rocket_thread_ready = threading.Event()
        self.last_rocket_pid = None
        self.edge_button = None

        # Roket modu için işlem öncelik seviyeleri / Process priority levels for rocket mode
        self.priority_levels = [
            ("Gerçek Zamanlı / Realtime", win32process.REALTIME_PRIORITY_CLASS),
            ("Yüksek / High", win32process.HIGH_PRIORITY_CLASS),
            ("Normalin Üstü / Above Normal", win32process.ABOVE_NORMAL_PRIORITY_CLASS),
            ("Normal", win32process.NORMAL_PRIORITY_CLASS),
            ("Normalin Altı / Below Normal", win32process.BELOW_NORMAL_PRIORITY_CLASS),
            ("Boşta / Idle", win32process.IDLE_PRIORITY_CLASS),
        ]
        self.selected_priority = win32process.HIGH_PRIORITY_CLASS
        self.selected_priority_name = "Yüksek / High"

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(10, 5, 10, 5)
        self.layout.setSpacing(10)
        self.setLayout(self.layout)

        self.close_btn = QPushButton("⨉")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("background-color: #e81123; color: white; border: none;")
        self.close_btn.clicked.connect(self.animate_and_close)
        self.layout.addWidget(self.close_btn)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Ara / Search or enter URL...")
        self.search_box.setFixedHeight(30)
        self.search_box.setFixedWidth(250)
        self.search_box.setStyleSheet("padding: 5px; background-color: #ffffff; color: black; border-radius: 5px;")
        self.search_box.returnPressed.connect(self.perform_search)
        self.layout.addWidget(self.search_box)

        self.engine_btn = QPushButton("🦆")
        self.engine_btn.setFixedSize(30, 30)
        self.engine_btn.setStyleSheet("background-color: #3e3e42; color: white; border: none; font-size: 16px;")
        self.engine_btn.clicked.connect(self.show_engine_menu)
        self.layout.addWidget(self.engine_btn)

        self.rocket_btn = QPushButton("🚀")
        self.rocket_btn.setFixedSize(30, 30)
        self.rocket_btn.setStyleSheet("background-color: #3e3e42; color: white; border: none; font-size: 16px;")
        self.rocket_btn.clicked.connect(self.toggle_rocket_mode)
        self.rocket_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rocket_btn.customContextMenuRequested.connect(self.show_priority_menu)
        self.rocket_btn.setToolTip(f"Roket Modu Önceliği / Priority: {self.selected_priority_name}")
        self.layout.addWidget(self.rocket_btn)

        self.clock_label = QLabel()
        self.clock_label.setFont(QFont("Arial", 11))
        self.layout.addStretch()
        self.layout.addWidget(self.clock_label)

        self.hide_btn = QPushButton("🡸")
        self.hide_btn.setFixedSize(30, 30)
        self.hide_btn.setStyleSheet("background-color: #3e3e42; color: white; border: none;")
        self.hide_btn.clicked.connect(self.hide_bar)
        self.layout.addWidget(self.hide_btn)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        self.clock_label.setText(QTime.currentTime().toString("HH:mm"))

    def show_engine_menu(self):
        menu = QMenu()
        menu.addAction("🔍 Google", lambda: self.set_engine("Google", "🔍"))
        menu.addAction("🟡 Yandex", lambda: self.set_engine("Yandex", "🟡"))
        menu.addAction("🦆 DuckDuckGo", lambda: self.set_engine("DuckDuckGo", "🦆"))
        menu.exec_(self.engine_btn.mapToGlobal(self.engine_btn.rect().bottomLeft()))

    def set_engine(self, engine, icon):
        self.selected_engine = engine
        self.engine_btn.setText(icon)

    def perform_search(self):
        query = self.search_box.text().strip()
        if not query:
            return
        if query.startswith("http://") or query.startswith("https://") or query.startswith("www."):
            if not query.startswith("http"):
                query = "https://" + query
            url = query
        else:
            if self.selected_engine == "Google":
                url = f"https://www.google.com/search?q={query}"
            elif self.selected_engine == "Yandex":
                url = f"https://yandex.com/search/?text={query}"
            else:
                url = f"https://duckduckgo.com/?q={query}"
        webbrowser.open(url)

    def show_priority_menu(self, pos):
        menu = QMenu()
        for name, level in self.priority_levels:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(level == self.selected_priority)
            action.triggered.connect(lambda checked, n=name, l=level: self.set_priority_level(n, l))
        menu.exec_(self.rocket_btn.mapToGlobal(pos))

    def set_priority_level(self, name, level):
        self.selected_priority = level
        self.selected_priority_name = name
        self.rocket_btn.setToolTip(f"Roket Modu Önceliği / Priority: {name}")

    def toggle_rocket_mode(self):
        if not self.rocket_mode_running:
            self.rocket_mode_running = True
            self.rocket_btn.setStyleSheet("background-color: green; color: white; border: none;")
            self.rocket_thread_id = None
            self.rocket_thread_ready.clear()
            self.rocket_thread = threading.Thread(target=self.run_rocket_mode, daemon=True)
            self.rocket_thread.start()
        else:
            self.rocket_mode_running = False
            self.rocket_btn.setStyleSheet("background-color: #3e3e42; color: white; border: none;")
            # Mesaj döngüsünün kurulmasını bekleyip WM_QUIT ile temiz şekilde durduruyoruz
            if self.rocket_thread_ready.wait(timeout=2) and self.rocket_thread_id:
                try:
                    win32api.PostThreadMessage(self.rocket_thread_id, win32con.WM_QUIT, 0, 0)
                except Exception as e:
                    print(f"Roket modu durdurma hatası / Rocket mode stop error:\n{e}")

    def is_excluded_process(self, pid):
        """Explorer, kabuk ve sistem süreçlerini roket modundan hariç tutar."""
        try:
            name = psutil.Process(pid).name().lower()
            return name in ROCKET_EXCLUDED_PROCESSES
        except Exception:
            # Süreç bilgisine erişilemiyorsa (ör. korumalı süreç), güvenli tarafta kal
            return True

    def apply_rocket_priority(self, hwnd):
        """Verilen pencerenin process'ine seçili önceliği uygular, öncekini normale döndürür."""
        if not hwnd:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception as e:
            print(f"Roket modu pencere okuma hatası / Rocket mode window read error:\n{e}")
            return
        if not pid or pid == self.last_rocket_pid or self.is_excluded_process(pid):
            return
        if self.last_rocket_pid:
            self.set_priority(self.last_rocket_pid, win32process.NORMAL_PRIORITY_CLASS)
        self.set_priority(pid, self.selected_priority)
        self.last_rocket_pid = pid

    def run_rocket_mode(self):
        self.last_rocket_pid = None
        self.rocket_thread_id = win32api.GetCurrentThreadId()

        def win_event_callback(hWinEventHook, event, hwnd, idObject, idChild, idEventThread, dwmsEventTime):
            if not self.rocket_mode_running:
                return
            try:
                self.apply_rocket_priority(hwnd)
            except Exception as e:
                print(f"Roket modu olay hatası / Rocket mode event error:\n{e}")

        # Callback referansını canlı tutmak zorunludur, yoksa çöp toplayıcı silebilir
        self._rocket_event_callback = WinEventProcType(win_event_callback)

        hook = None
        if self.rocket_mode_running:
            try:
                hook = ctypes.windll.user32.SetWinEventHook(
                    EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
                    0, self._rocket_event_callback, 0, 0, WINEVENT_OUTOFCONTEXT
                )
            except Exception as e:
                print(f"Roket modu kanca hatası / Rocket mode hook error:\n{e}")
                hook = None

        # Ana thread'in WM_QUIT gönderebilmesi için hazır olduğumuzu bildiriyoruz
        self.rocket_thread_ready.set()

        # Mevcut aktif pencereye hemen öncelik uygula
        if self.rocket_mode_running:
            try:
                self.apply_rocket_priority(win32gui.GetForegroundWindow())
            except Exception as e:
                print(f"Roket modu başlatma hatası / Rocket mode init error:\n{e}")

        if hook and self.rocket_mode_running:
            # Olay tabanlı, CPU dostu mesaj döngüsü / event-driven, CPU-friendly loop
            win32gui.PumpMessages()
            ctypes.windll.user32.UnhookWinEvent(hook)
        elif hook:
            ctypes.windll.user32.UnhookWinEvent(hook)
        elif self.rocket_mode_running:
            # Kanca kurulamazsa güvenli bir yedek olarak polling'e düş, hatada da bekle
            while self.rocket_mode_running:
                try:
                    self.apply_rocket_priority(win32gui.GetForegroundWindow())
                except Exception as e:
                    print(f"Roket modu hatası / Rocket mode error:\n{e}")
                time.sleep(1)

        # Roket modu kapanınca son işlenen süreci normal önceliğe geri döndür
        if self.last_rocket_pid:
            self.set_priority(self.last_rocket_pid, win32process.NORMAL_PRIORITY_CLASS)
            self.last_rocket_pid = None
        self.rocket_mode_running = False

    def set_priority(self, pid, priority_level):
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, False, pid)
            win32process.SetPriorityClass(handle, priority_level)
            win32api.CloseHandle(handle)
        except Exception as e:
            # Hata varsa konsola yazdırıyoruz
            print(f"Öncelik ayarlama hatası / Priority setting error (PID {pid}):\n{e}")

    def show_error(self, message):
        # Qt event sistemine uygun hata gösterme, güvenli thread kullanımı
        QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Hata / Error", message))

    def animate_and_close(self):
        final_width = self.close_btn.width() + 20
        final_rect = QRect(self.x(), self.y(), final_width, self.height())
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(600)
        self.animation.setEndValue(final_rect)
        self.animation.finished.connect(self.close)
        self.animation.start()

    def hide_bar(self):
        self.hide()
        self.edge_button = EdgeButton(self.show_bar)
        self.edge_button.show()

    def show_bar(self):
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

if __name__ == "__main__":
    bar = RocketTaskbar()
    bar.setGeometry(300, 700, 600, 50)
    bar.show()
    sys.exit(app.exec_())
