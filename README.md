# GestureFlow

GestureFlow is a Windows 10/11 x64 desktop utility for webcam-based cursor navigation, pinch drag/click, right click, scrolling, and zoom gestures. It uses a dedicated Qt camera thread, MediaPipe hand landmarks, a debounced gesture state machine, and a small always-on-top HUD. Settings are written atomically to `config.json`; logs are stored in `%USERPROFILE%\\.gestureflow\\gestureflow.log`.

## Install and run

Use 64-bit Python 3.10–3.12 (Python 3.11 is recommended). MediaPipe is pinned to 0.10.21 because newer releases in the 0.10 series removed the `mp.solutions` API used by this application. In PowerShell from this directory:

```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Allow camera access in Windows privacy settings. Defaults are tuned for mid-range laptop CPUs (640×480 capture, 30 FPS, MediaPipe's lightweight model); the 2 GB GPU is not required. GestureFlow starts in the notification area; use its tray menu to pause, show/hide the HUD, adjust settings, or exit. Close via the tray menu rather than killing the process so any held mouse button is released. The default camera mapping reserves a 15% border on each side.

## Gestures

- Index extended, other fingers curled: move the cursor.
- Thumb/index pinch: hold left mouse button while pinched (drag); release by separating.
- Thumb/middle pinch with index raised: right click.
- Index and middle extended and close: scroll by moving the hand vertically.
- Thumb/index pinch with the other three fingers extended: zoom by expanding/contracting pinch distance.

Gesture recognition depends on camera angle, lighting, and individual hand anatomy. Tune pinch threshold, scroll deadzone, camera and smoothing under tray → Settings. Use the tray pause action before typing sensitive text.

## Build portable Windows executable

From a clean Windows x64 environment with dependencies installed:

```powershell
pyinstaller --noconfirm --onedir --windowed --name GestureFlow --collect-all mediapipe --collect-all cv2 --collect-all PyQt6 main.py
```

The directory distribution is written to `dist\\GestureFlow`. Keep the adjacent runtime files together. Camera drivers and Windows camera privacy permissions are still required.

## Engineering notes

Camera reads run on a stoppable `QThread` with retry/backoff and status notifications. A lock-protected one-frame mailbox drops stale camera frames; a Qt timer consumes only the newest image at up to 25 FPS, preventing queued frame signals from accumulating when inference is slower than capture. Landmark processing and input synthesis run on the Qt thread, avoiding cross-thread MediaPipe and controller access. OS operations are guarded and the left button is released on pause, hand loss, and shutdown. Configuration load tolerates missing or malformed files and writes use atomic replacement. Emergency pause is available with Ctrl+Shift+Esc or by moving the pointer to the top-left screen corner; the corner trigger rearms after the pointer leaves.
