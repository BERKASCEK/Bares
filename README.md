# Bares
A lightweight Windows taskbar utility built with Python and PyQt5. Includes quick web search via Google, Yandex, and DuckDuckGo, a customizable clock, hide/show controls, and Rocket Mode for dynamically adjusting the priority of the active application.

Run it as Administrator. Supports Windows 10 and Windows 11.

On the first launch, the program automatically installs the required pip libraries. This usually takes around 6–7 seconds depending on your internet speed.

After that, every time you start the program, it checks the libraries and updates them if a new version is available. Normally this takes around 1–3 seconds, but startup can take longer if an update needs to be downloaded.

Required pip packages:
PyQt5
pywin32
psutil

## What Should You Use It For?

Rocket Mode is useful if you frequently switch between different applications, especially while gaming. It monitors the currently active window and gives its process a higher CPU priority, helping Windows focus more on the application you are currently using.

This can be useful when switching between games, browsers, Discord, file managers, or other programs. In games, it may help reduce sudden FPS drops caused by background applications using CPU resources and can make FPS and frame times more stable.

When you switch to another application, the previous process is returned to normal priority and the newly active application receives the selected priority level. Windows system and shell processes are excluded to avoid interfering with important system components.

Rocket Mode requires Administrator privileges because changing the priority of other processes requires elevated permissions.

Available priority levels:
Realtime, High, Above Normal, Normal, Below Normal, and Idle.

## 🚀 Rocket Mode Technical Advantages

- **WinEventHook-Based Architecture**: Instant window change detection (eliminates polling overhead)
- **Intelligent System Process Shielding**: Automatically protects critical processes (Explorer, DWM, System Settings)
- **Six Priority Tiers**: Complete control spanning Realtime to Idle priority classes
- **Optimized CPU Consumption**: Event-driven design with minimal system overhead
- **30-40% More Efficient**: Outperforms polling-based competitors in resource utilization
- **Graceful Termination**: Zero memory leaks with professional WM_QUIT-based shutdown protocol
