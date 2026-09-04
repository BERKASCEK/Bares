import sys
import os
import json
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
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QMenu, QMessageBox, QDialog, QListWidget, QFileDialog, QInputDialog
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
# Özel işlev butonları (roket modunun sağındaki 5 buton) ayarları
# --------------------------
SLOT_COUNT = 5
SETTINGS_FILENAME = "Bares_ayarların.txt"


def get_settings_path():
    return os.path.join(os.path.expanduser("~"), SETTINGS_FILENAME)


def default_slot():
    return {"type": None, "label": "+", "data": {}}


def get_installed_apps():
    """
    Başlat Menüsü kısayollarını tarayarak bilgisayardaki uygulamaların bir
    listesini çıkarır. / Scans the Start Menu shortcuts to build a list of
    installed applications on the computer.
    """
    apps = {}
    search_dirs = []
    program_data = os.environ.get("ProgramData")
    appdata = os.environ.get("APPDATA")
    if program_data:
        search_dirs.append(os.path.join(program_data, "Microsoft", "Windows", "Start Menu", "Programs"))
    if appdata:
        search_dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))

    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower().endswith((".lnk", ".exe")):
                    name = os.path.splitext(f)[0]
                    if name and name not in apps:
                        apps[name] = os.path.join(root, f)
    return apps


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
# Komut yazma penceresi (CMD / PowerShell)
# --------------------------
class CommandDialog(QDialog):
    def __init__(self, parent, shell_type, current_command=""):
        super().__init__(parent)
        title = "CMD Komutu" if shell_type == "cmd" else "PowerShell Komutu"
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        note = QLabel(
            "⚠️ Bu komut Yönetici (Admin) olarak çalıştırılacaktır.\n"
            "This command will be run as Administrator."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #b35900; font-weight: bold;")
        layout.addWidget(note)

        layout.addWidget(QLabel("Komut / Command:"))
        self.command_edit = QLineEdit(current_command)
        self.command_edit.setPlaceholderText("örn: ipconfig /all")
        layout.addWidget(self.command_edit)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Kaydet / Save")
        cancel_btn = QPushButton("İptal / Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_command(self):
        return self.command_edit.text().strip()


# --------------------------
# Bilgisayardan yazılım seçme penceresi
# --------------------------
class AppSelectorDialog(QDialog):
    def __init__(self, parent, apps):
        super().__init__(parent)
        self.setWindowTitle("Bilgisayardan Yazılım Seç / Select Installed Software")
        self.setMinimumSize(420, 480)

        self.apps = apps
        self.selected_path = None
        self.selected_name = None
        self.selected_type = None

        layout = QVBoxLayout(self)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ara / Search...")
        self.search_edit.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept_selection())
        layout.addWidget(self.list_widget)
        self.populate_list(apps)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("➕ Ekle / Add")
        self.add_btn.clicked.connect(self.accept_selection)
        btn_row.addWidget(self.add_btn)

        cancel_btn = QPushButton("İptal / Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.advanced_btn = QPushButton("📁 Gelişmiş: Uygulama/Yazılım Seç (Dosyalardan...) / Advanced: Browse Files...")
        self.advanced_btn.clicked.connect(self.browse_file)
        layout.addWidget(self.advanced_btn)

    def populate_list(self, apps):
        self.list_widget.clear()
        for name in sorted(apps.keys(), key=str.lower):
            self.list_widget.addItem(name)

    def filter_list(self, text):
        text = text.lower().strip()
        if not text:
            self.populate_list(self.apps)
            return
        filtered = {n: p for n, p in self.apps.items() if text in n.lower()}
        self.populate_list(filtered)

    def accept_selection(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Bilgi / Info",
                                     "Lütfen bir uygulama seçin. / Please select an application.")
            return
        name = item.text()
        self.selected_name = name
        self.selected_path = self.apps.get(name)
        self.selected_type = "app"
        self.accept()

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Dosyalardan Seç / Select From Files", "",
            "Programlar / Programs (*.exe);;Tüm Dosyalar / All Files (*.*)"
        )
        if path:
            self.selected_path = path
            self.selected_name = os.path.splitext(os.path.basename(path))[0]
            self.selected_type = "file"
            self.accept()


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
        self._saved_geometry = None

        # Roket modunun sağındaki 5 özel işlev butonu / 5 custom function slots
        self.function_slots = [default_slot() for _ in range(SLOT_COUNT)]
        self.function_buttons = []

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

        # --- Roket modu butonunun sağındaki 5 özel işlev butonu ---
        for i in range(SLOT_COUNT):
            btn = QPushButton("+")
            btn.setFixedSize(30, 30)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, idx=i: self.show_slot_menu(idx, pos))
            btn.clicked.connect(lambda checked=False, idx=i: self.handle_slot_click(idx))
            self.layout.addWidget(btn)
            self.function_buttons.append(btn)
            self.update_slot_button(i)

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

        # Kayıtlı ayarları yükle (varsa) / Load saved settings (if any)
        self.load_settings()

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
        self.save_settings()

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
        self.save_settings()

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

    # --------------------------
    # Özel işlev butonları (roket modunun sağındaki 5 buton)
    # --------------------------
    def show_slot_menu(self, idx, pos):
        slot = self.function_slots[idx]
        menu = QMenu()
        if slot.get("type"):
            reassign_menu = menu.addMenu("✏️ Yeniden Ata / Reassign")
            self._add_assign_actions(reassign_menu, idx)
            menu.addSeparator()
            menu.addAction("🗑️ Kaldır / Remove", lambda: self.remove_slot(idx))
        else:
            self._add_assign_actions(menu, idx)
        menu.exec_(self.function_buttons[idx].mapToGlobal(pos))

    def _add_assign_actions(self, menu, idx):
        menu.addAction("🖥️ CMD Komutu Ekle/Düzenle", lambda: self.assign_shell(idx, "cmd"))
        menu.addAction("💻 PowerShell Komutu Ekle/Düzenle", lambda: self.assign_shell(idx, "powershell"))
        menu.addAction("📦 Bilgisayardan Yazılım Seç", lambda: self.assign_app(idx))
        menu.addAction("🌐 İnternet Sayfası Ekle/Düzenle", lambda: self.assign_url(idx))

    def handle_slot_click(self, idx):
        slot = self.function_slots[idx]
        t = slot.get("type")
        if t is None:
            # Boş buton: kolaylık olsun diye sol tıkta da atama menüsünü göster
            self.show_slot_menu(idx, self.function_buttons[idx].rect().bottomLeft())
            return
        try:
            if t == "cmd":
                self.run_elevated_shell("cmd", slot["data"].get("command", ""))
            elif t == "powershell":
                self.run_elevated_shell("powershell", slot["data"].get("command", ""))
            elif t in ("app", "file"):
                os.startfile(slot["data"].get("path", ""))
            elif t == "url":
                webbrowser.open(slot["data"].get("url", ""))
        except Exception as e:
            self.show_error(f"Çalıştırma hatası / Execution error:\n{e}")

    def assign_shell(self, idx, shell_type):
        slot = self.function_slots[idx]
        current = slot["data"].get("command", "") if slot.get("type") == shell_type else ""
        dlg = CommandDialog(self, shell_type, current)
        if dlg.exec_() == QDialog.Accepted:
            command = dlg.get_command()
            if not command:
                return
            self.function_slots[idx] = {
                "type": shell_type,
                "label": "CMD" if shell_type == "cmd" else "PS",
                "data": {"command": command},
            }
            self.update_slot_button(idx)
            self.save_settings()

    def assign_app(self, idx):
        apps = get_installed_apps()
        dlg = AppSelectorDialog(self, apps)
        if dlg.exec_() == QDialog.Accepted and dlg.selected_path:
            name = dlg.selected_name or "APP"
            label = name[:4] if len(name) > 4 else name
            self.function_slots[idx] = {
                "type": dlg.selected_type,
                "label": label,
                "data": {"path": dlg.selected_path, "name": name},
            }
            self.update_slot_button(idx)
            self.save_settings()

    def assign_url(self, idx):
        slot = self.function_slots[idx]
        current = slot["data"].get("url", "") if slot.get("type") == "url" else ""
        url, ok = QInputDialog.getText(
            self, "İnternet Sayfası / Web Page", "URL girin / Enter URL:", QLineEdit.Normal, current
        )
        if ok and url.strip():
            url = url.strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url
            try:
                domain = url.split("//", 1)[1].split("/", 1)[0]
            except Exception:
                domain = url
            label = domain.replace("www.", "")[:6] or "WEB"
            self.function_slots[idx] = {
                "type": "url",
                "label": label,
                "data": {"url": url},
            }
            self.update_slot_button(idx)
            self.save_settings()

    def remove_slot(self, idx):
        self.function_slots[idx] = default_slot()
        self.update_slot_button(idx)
        self.save_settings()

    def update_slot_button(self, idx):
        slot = self.function_slots[idx]
        btn = self.function_buttons[idx]
        btn.setText(slot.get("label", "+"))
        t = slot.get("type")
        if t is None:
            btn.setStyleSheet("background-color: #3e3e42; color: white; border: none; font-size: 16px;")
            btn.setToolTip("Boş / Empty — Sağ tıklayarak işlev atayın / Right-click to assign a function")
        else:
            btn.setStyleSheet("background-color: #0078d7; color: white; border: none; font-size: 10px;")
            data = slot.get("data", {})
            if t == "cmd":
                btn.setToolTip(f"CMD (Yönetici/Admin):\n{data.get('command', '')}")
            elif t == "powershell":
                btn.setToolTip(f"PowerShell (Yönetici/Admin):\n{data.get('command', '')}")
            elif t in ("app", "file"):
                btn.setToolTip(f"{data.get('name', '')}\n{data.get('path', '')}")
            elif t == "url":
                btn.setToolTip(data.get("url", ""))

    def run_elevated_shell(self, shell_type, command):
        if not command:
            return
        try:
            if shell_type == "cmd":
                exe = "cmd.exe"
                params = f'/k "{command}"'
            else:
                exe = "powershell.exe"
                escaped = command.replace('"', '\\"')
                params = f'-NoExit -Command "{escaped}"'
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        except Exception as e:
            self.show_error(f"Komut çalıştırılamadı / Command execution failed:\n{e}")

    # --------------------------
    # Ayarları kaydetme / yükleme
    # --------------------------
    def save_settings(self):
        try:
            data = {
                "selected_engine": self.selected_engine,
                "selected_priority_name": self.selected_priority_name,
                "geometry": {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()},
                "function_slots": self.function_slots,
            }
            with open(get_settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ayarlar kaydedilemedi / Settings could not be saved:\n{e}")

    def load_settings(self):
        path = get_settings_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.selected_engine = data.get("selected_engine", self.selected_engine)
            engine_icons = {"Google": "🔍", "Yandex": "🟡", "DuckDuckGo": "🦆"}
            self.engine_btn.setText(engine_icons.get(self.selected_engine, "🦆"))

            priority_name = data.get("selected_priority_name")
            if priority_name:
                for name, level in self.priority_levels:
                    if name == priority_name:
                        self.selected_priority = level
                        self.selected_priority_name = name
                        self.rocket_btn.setToolTip(f"Roket Modu Önceliği / Priority: {name}")
                        break

            saved_slots = data.get("function_slots")
            if isinstance(saved_slots, list) and len(saved_slots) == SLOT_COUNT:
                self.function_slots = saved_slots
                for i in range(SLOT_COUNT):
                    self.update_slot_button(i)

            self._saved_geometry = data.get("geometry")
        except Exception as e:
            print(f"Ayarlar yüklenemedi / Settings could not be loaded:\n{e}")

    def show_error(self, message):
        # Qt event sistemine uygun hata gösterme, güvenli thread kullanımı
        QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Hata / Error", message))

    def animate_and_close(self):
        self.save_settings()
        final_width = self.close_btn.width() + 20
        final_rect = QRect(self.x(), self.y(), final_width, self.height())
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(600)
        self.animation.setEndValue(final_rect)
        self.animation.finished.connect(self.close)
        self.animation.start()

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)

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
    geo = getattr(bar, "_saved_geometry", None)
    if geo:
        bar.setGeometry(geo.get("x", 300), geo.get("y", 700), geo.get("w", 850), geo.get("h", 50))
    else:
        bar.setGeometry(300, 700, 850, 50)
    bar.show()
    sys.exit(app.exec_())
