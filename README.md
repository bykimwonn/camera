# BT CURSOR

BT CURSOR is a Windows 10/11 x64 webcam cursor-control app. Its main window lets you choose independent **Hand gestures** or **Head cursor** mode, open settings, pause control, and toggle a live camera HUD. Hand mode keeps cursor movement, pinch click/drag, right-click, scroll, and zoom. Head mode moves the cursor with face/head position, performs a configurable dwell click, and scrolls when the pointer is held at the top or bottom screen edge. It uses local MediaPipe landmarks only for tracking; it does not identify people or save camera frames. Settings are written atomically; logs remain in `%USERPROFILE%\\.gestureflow\\gestureflow.log` for compatibility.

## Install and run

Use 64-bit Python 3.10–3.12 (Python 3.11 is recommended). MediaPipe is pinned to 0.10.21 because newer releases in the 0.10 series removed the `mp.solutions` API used by this application. In PowerShell from this directory:

```powershell
py -3.11 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Allow camera access in Windows privacy settings. Defaults are tuned for laptop CPUs (320×240 at 15 FPS; the 2 GB GPU is not required). Camera index 0 and capture settings are shared by Hand and Head modes; camera numbering varies, so choose the working laptop webcam in Settings if needed. The BT CURSOR window opens directly. Select a mode card to switch immediately; **Settings** contains dwell timing and click action choices. Head mode defaults to a one-second dwell for left-click, with right-click and double-click available in Settings. To scroll, move the head-controlled cursor to the top or bottom screen edge and hold briefly; moving away after a click re-arms it. Enable **Show camera HUD** to see the tracked face box and current action. A visible-light camera needs illumination; the T480 IR camera must be accessible to OpenCV. No head calibration is required.

## Gestures

- **Move:** hold only the index finger up; curl middle, ring, and pinky. Move your hand left/right to move the pointer left/right (horizontal inversion is enabled by default and configurable).
- **Left click:** with middle, ring, and pinky curled, briefly touch thumb to index, then release. A short pinch is a click; it does not hold the mouse button.
- **Drag:** start the same thumb/index pinch and hold it for the configured delay (450 ms by default). Once the HUD says `DRAGGING`, move; separate thumb and index to release. Releasing before the delay clicks instead.
- **Right click:** raise index and touch thumb to middle. Release fully before another right click; it fires once per pinch.
- **Scroll:** extend index and middle close together, curl ring and pinky, and keep the thumb away from both fingertips. Pause briefly to establish the anchor, then move the pair a small distance up/down. Deadzone and sensitivity are adjustable.
- **Zoom:** extend middle, ring, and pinky, then bring thumb and index close together to arm zoom. Keep the three fingers extended and open/close the thumb-index gap to zoom in/out.

Gesture recognition depends on camera angle, lighting, and individual hand anatomy. Tune pinch threshold, scroll deadzone, camera and smoothing under tray → Settings. Use the tray pause action before typing sensitive text.

## Capture a debug session (Windows)

Run `run-debug.ps1` from PowerShell or double-click `run-debug.cmd` from Command Prompt/the Explorer. The script launches the app and saves the combined console/error output as `%USERPROFILE%\\.gestureflow\\session-<timestamp>.txt`. BT CURSOR also writes `motion.jsonl` (timestamped hand-tip or head-center cursor samples, mapped and filtered cursor positions, movement delta, dwell progress/click events, whether each sample reached the OS, gesture/frame state) plus the rotating `gestureflow.log` error log in `%USERPROFILE%\\.gestureflow`. No camera frames or images are recorded. Cursor coordinates can reveal screen activity; review the files before sharing.

After closing the app, show the latest session and motion samples in PowerShell:

```powershell
Get-Content (Get-ChildItem "$HOME\\.gestureflow\\session-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 200
Get-Content "$HOME\\.gestureflow\\motion.jsonl" -Tail 200
Get-Content "$HOME\\.gestureflow\\gestureflow.log" -Tail 200
```

Copy the relevant output and paste it into the debugging chat. Motion samples rotate automatically to bound disk use. Diagnostics are written on a background queue so disk logging does not stall tracking; the camera reader also downsizes frames if a driver ignores the requested 320×240 size. The launcher tolerates Qt's benign `SetProcessDpiAwarenessContext() failed` warning instead of aborting.

## Build a single Windows executable

On Windows, after installing dependencies, run:

```powershell
.\.venv\Scripts\Activate.ps1
.\build_windows.ps1
```

The script builds one windowed file at `dist\BT CURSOR.exe` with the BT CURSOR icon and bundled MediaPipe/OpenCV/Qt assets. This one-file build can take a few minutes and starts more slowly than running from Python. Double-click the EXE to open the mode-selection/settings window; no console is shown. Settings and logs stay under `%USERPROFILE%\.gestureflow` so they survive app updates. You can pin `dist\BT CURSOR.exe` to the taskbar from File Explorer. Windows camera drivers and camera privacy permissions are still required.

## Engineering notes

Camera reads run on a stoppable `QThread` with retry/backoff and status notifications. A lock-protected one-frame mailbox drops stale camera frames; a Qt timer consumes only the newest image at up to 20 FPS, preventing queued frame signals from accumulating when inference is slower than capture. Landmark processing and input synthesis run on the Qt thread, avoiding cross-thread MediaPipe and controller access. OS operations are guarded; hand gestures are released on pause, hand loss, and shutdown. Head dwell clicks are one-shot and require moving away before re-arming. Configuration load tolerates missing or malformed files and writes use atomic replacement. Emergency pause is available with Ctrl+Shift+Esc or by moving the pointer to the top-left screen corner; the corner trigger rearms after the pointer leaves.
