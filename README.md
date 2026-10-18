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

Allow camera access in Windows privacy settings. Defaults are tuned for mid-range laptop CPUs (640×480 capture, 30 FPS, MediaPipe's lightweight model); the 2 GB GPU is not required. GestureFlow starts in the notification area; use its tray menu to pause, show/hide the HUD, adjust settings, or exit. Close via the tray menu rather than killing the process so any held mouse button is released. The default camera mapping reserves a 20% border on each side; Settings → Control → `Cursor reach` changes the physical movement range (higher values require less hand travel). Settings → Control → `Jitter deadband` suppresses tiny cursor tremors (start at 6 px; increase to 8–10 px if it still shakes, decrease if small cursor movements feel ignored). A lower `Filter cutoff` steadies the cursor but adds lag; increase `Filter response` to reduce lag during fast movements.

## Gestures

- **Move:** hold only the index finger up; curl middle, ring, and pinky. Move your hand left/right to move the pointer left/right (horizontal inversion is enabled by default and configurable).
- **Left click:** with middle, ring, and pinky curled, briefly touch thumb to index, then release. A short pinch is a click; it does not hold the mouse button.
- **Drag:** start the same thumb/index pinch and hold it for the configured delay (450 ms by default). Once the HUD says `DRAGGING`, move; separate thumb and index to release. Releasing before the delay clicks instead.
- **Right click:** raise index and touch thumb to middle. Release fully before another right click; it fires once per pinch.
- **Scroll:** extend index and middle close together, curl ring and pinky, and keep the thumb away from both fingertips. Pause briefly to establish the anchor, then move the pair a small distance up/down. Deadzone and sensitivity are adjustable.
- **Zoom:** extend middle, ring, and pinky, then bring thumb and index close together to arm zoom. Keep the three fingers extended and open/close the thumb-index gap to zoom in/out.

Gesture recognition depends on camera angle, lighting, and individual hand anatomy. Tune pinch threshold, scroll deadzone, camera and smoothing under tray → Settings. Use the tray pause action before typing sensitive text.

## Build portable Windows executable

From a clean Windows x64 environment with dependencies installed:

```powershell
pyinstaller --noconfirm --onedir --windowed --name GestureFlow --collect-all mediapipe --collect-all cv2 --collect-all PyQt6 main.py
```

The directory distribution is written to `dist\\GestureFlow`. Keep the adjacent runtime files together. Camera drivers and Windows camera privacy permissions are still required.

## Engineering notes

Camera reads run on a stoppable `QThread` with retry/backoff and status notifications. A lock-protected one-frame mailbox drops stale camera frames; a Qt timer consumes only the newest image at up to 25 FPS, preventing queued frame signals from accumulating when inference is slower than capture. Landmark processing and input synthesis run on the Qt thread, avoiding cross-thread MediaPipe and controller access. OS operations are guarded and the left button is released on pause, hand loss, and shutdown. Configuration load tolerates missing or malformed files and writes use atomic replacement. Emergency pause is available with Ctrl+Shift+Esc or by moving the pointer to the top-left screen corner; the corner trigger rearms after the pointer leaves.
