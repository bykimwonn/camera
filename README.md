# GestureFlow

GestureFlow is a Windows 10/11 x64 desktop utility for webcam-based cursor navigation, pinch drag/click, right click, scrolling, and zoom gestures. It uses a dedicated Qt camera thread, MediaPipe hand landmarks, a debounced gesture state machine, and an optional floating HUD (hidden by default). Settings are written atomically to `config.json`; logs are stored in `%USERPROFILE%\\.gestureflow\\gestureflow.log`.

## Install and run

Use 64-bit Python 3.10–3.12 (Python 3.11 is recommended). MediaPipe is pinned to 0.10.21 because newer releases in the 0.10 series removed the `mp.solutions` API used by this application. In PowerShell from this directory:

```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Allow camera access in Windows privacy settings. Defaults are tuned for laptop CPUs (320×240 at 15 FPS; the 2 GB GPU is not required). The default camera index is 0 and the same camera selection and capture settings are shared by Hand and Head modes. Camera numbering varies, so choose the working laptop webcam's device index in Settings → Control if needed. GestureFlow starts in the notification area with the HUD hidden. Settings remain available from the tray. Choose **Hand gestures** or **Head movement + dwell click** from the tray's Cursor Control Mode submenu; they are mutually exclusive. Hand mode supports cursor, clicks, drag, scroll, and zoom. Head mode moves the pointer from the face/head position and left-clicks when the cursor stays still over a spot for the configured dwell time (one second by default). No gaze calibration is required. Head landmarks are processed locally only to locate the current face; the app does not identify people or save camera frames.

Tray → Settings lets you adjust the dwell-click time, choose the camera, tune hand detection/tracking confidence, turn on automatic low-light enhancement, show/hide the HUD, and adjust cursor/gesture settings. A visible-light camera still needs illumination; the T480 IR camera must be accessible to OpenCV. The default mapping reserves a 20% border; higher `Cursor reach` means less head/hand travel but more cursor gain. Move the head away from a clicked spot to re-arm for the next dwell click.

## Gestures

- **Move:** hold only the index finger up; curl middle, ring, and pinky. Move your hand left/right to move the pointer left/right (horizontal inversion is enabled by default and configurable).
- **Left click:** with middle, ring, and pinky curled, briefly touch thumb to index, then release. A short pinch is a click; it does not hold the mouse button.
- **Drag:** start the same thumb/index pinch and hold it for the configured delay (450 ms by default). Once the HUD says `DRAGGING`, move; separate thumb and index to release. Releasing before the delay clicks instead.
- **Right click:** raise index and touch thumb to middle. Release fully before another right click; it fires once per pinch.
- **Scroll:** extend index and middle close together, curl ring and pinky, and keep the thumb away from both fingertips. Pause briefly to establish the anchor, then move the pair a small distance up/down. Deadzone and sensitivity are adjustable.
- **Zoom:** extend middle, ring, and pinky, then bring thumb and index close together to arm zoom. Keep the three fingers extended and open/close the thumb-index gap to zoom in/out.

Gesture recognition depends on camera angle, lighting, and individual hand anatomy. Tune pinch threshold, scroll deadzone, camera and smoothing under tray → Settings. Use the tray pause action before typing sensitive text.

## Capture a debug session (Windows)

Run `run-debug.ps1` from PowerShell or double-click `run-debug.cmd` from Command Prompt/the Explorer. The script launches the app and saves the combined console/error output as `%USERPROFILE%\\.gestureflow\\session-<timestamp>.txt`. GestureFlow also writes `motion.jsonl` (timestamped hand-tip or head-center cursor samples, mapped and filtered cursor positions, movement delta, dwell progress/click events, whether each sample reached the OS, gesture/frame state) plus the rotating `gestureflow.log` error log in `%USERPROFILE%\\.gestureflow`. No camera frames or images are recorded. Cursor coordinates can reveal screen activity; review the files before sharing.

After closing the app, show the latest session and motion samples in PowerShell:

```powershell
Get-Content (Get-ChildItem "$HOME\\.gestureflow\\session-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 200
Get-Content "$HOME\\.gestureflow\\motion.jsonl" -Tail 200
Get-Content "$HOME\\.gestureflow\\gestureflow.log" -Tail 200
```

Copy the relevant output and paste it into the debugging chat. Motion samples rotate automatically to bound disk use. Diagnostics are written on a background queue so disk logging does not stall tracking; the camera reader also downsizes frames if a driver ignores the requested 320×240 size. The launcher tolerates Qt's benign `SetProcessDpiAwarenessContext() failed` warning instead of aborting.

## Build portable Windows executable

From a clean Windows x64 environment with dependencies installed:

```powershell
pyinstaller --noconfirm --clean --onedir --windowed --name GestureFlow --icon assets\gestureflow.ico --add-data "assets;assets" --collect-all mediapipe --collect-all cv2 --collect-all PyQt6 main.py
```

The directory distribution is written to `dist\\GestureFlow`. Keep the adjacent runtime files together. The executable and tray use the included custom GestureFlow icon. To pin it, open `dist\\GestureFlow\\GestureFlow.exe` in File Explorer, right-click it, and choose **Pin to taskbar** (or **Show more options → Pin to taskbar**). The frozen app stores settings under `%USERPROFILE%\\.gestureflow\\config.json`, so settings survive moving the distribution folder. Camera drivers and Windows camera privacy permissions are still required.

## Engineering notes

Camera reads run on a stoppable `QThread` with retry/backoff and status notifications. A lock-protected one-frame mailbox drops stale camera frames; a Qt timer consumes only the newest image at up to 20 FPS, preventing queued frame signals from accumulating when inference is slower than capture. Landmark processing and input synthesis run on the Qt thread, avoiding cross-thread MediaPipe and controller access. OS operations are guarded; hand gestures are released on pause, hand loss, and shutdown. Head dwell clicks are one-shot and require moving away before re-arming. Configuration load tolerates missing or malformed files and writes use atomic replacement. Emergency pause is available with Ctrl+Shift+Esc or by moving the pointer to the top-left screen corner; the corner trigger rearms after the pointer leaves.
