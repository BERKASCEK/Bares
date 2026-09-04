# Bares

A lightweight Windows taskbar utility built with Python and PyQt5. Includes quick web search via Google, Yandex, and DuckDuckGo, a customizable clock, hide/show controls, 5 fully customizable function buttons, and Rocket Mode for dynamically adjusting the priority of the active application.

Run it as Administrator. Supports Windows 10 and Windows 11.

On the first launch, the program automatically installs the required Python packages. This usually takes about 1–2 minutes, depending on your internet speed. After that, every time you start the program, it checks the libraries and updates them if a new version is available — normally 1–3 seconds, longer only if an update needs to be downloaded.

**Required pip packages:** PyQt5 · pywin32 · psutil

## Rocket Mode

Useful if you frequently switch between applications, especially while gaming. It monitors the active window and gives its process a higher CPU priority, so Windows focuses more on whatever you're currently using — games, browsers, Discord, file managers, etc. This can help reduce sudden FPS drops caused by background apps eating CPU time.

When you switch windows, the previous process returns to Normal priority and the newly focused one gets the selected level. System/shell processes (Explorer, DWM, System Settings, etc.) are excluded automatically. Requires Administrator privileges since changing another process's priority needs elevation.

**Priority levels:** Realtime, High, Above Normal, Normal, Below Normal, Idle

### 🚀 Technical Advantages
- **WinEventHook-based** — instant window-change detection, no polling overhead
- **System process shielding** — critical processes are auto-protected
- **Six priority tiers** — full control from Realtime to Idle
- **Event-driven, low CPU** — 30–40% more efficient than polling-based alternatives
- **Clean shutdown** — WM_QUIT-based termination, zero memory leaks

## Custom Function Buttons

Five customizable slots sit to the right of the Rocket Mode button. Each starts empty, shown as **"+"**.

**Assigning a slot** — right-click (or left-click) an empty slot to choose:
| Option | What it does |
|---|---|
| **CMD** | Save a command; the dialog clearly states it will run **as Administrator**. Runs elevated (`runas`) in a persistent CMD window. |
| **PowerShell** | Same as above, elevated PowerShell (`-NoExit`). |
| **Select Installed Software** | Scans your Start Menu shortcuts with a searchable picker → pick one → **Add**. Includes an **Advanced: Browse Files...** button to pick *any* file/executable directly from disk. |
| **Web Page** | Enter a URL; opens in your default browser. |

An assigned slot can be **reassigned** or **removed** via right-click at any time. Left-clicking a filled slot runs its action immediately.

## Settings

Everything — search engine, Rocket Mode priority, window position, and all 5 function-button assignments — is saved automatically to:

```
%USERPROFILE%\Bares_ayarların.txt
```

(plain JSON). Loaded automatically on next launch — no setup needed.

## License

Bares License
Copyright © 2026 BERKASCEK
Redistribution prohibited.
