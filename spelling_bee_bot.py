import sounddevice as sd
import numpy as np
from scipy.io import wavfile
import speech_recognition as sr
import time
import random
import string
import sys
import os
import platform
import threading
import queue
import hashlib
from difflib import SequenceMatcher
from pynput import keyboard as pynput_keyboard

# ─── Platform Detection ──────────────────────────────────────────────
IS_MACOS = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"

# ─── Cross-platform Keyboard Abstraction ─────────────────────────────
# Windows  → uses the `keyboard` library (fast, no root needed)
# macOS    → uses `pynput.keyboard.Controller` (no sudo required)
if IS_MACOS:
    from pynput.keyboard import Controller as _PynputController, Key as _PynputKey, KeyCode as _PynputKeyCode
    _kb_controller = _PynputController()
    _PYNPUT_SPECIAL = {
        "backspace": _PynputKey.backspace,
        "enter":     _PynputKey.enter,
        "shift":     _PynputKey.shift,
        "ctrl":      _PynputKey.ctrl_l,
        "alt":       _PynputKey.alt_l,
    }

    # Pre-compute KeyCode objects for every character we'll ever type.
    # pynput's .type(char) calls KeyCode.from_char() on every single keystroke,
    # which does a unicode lookup through macOS Accessibility — significant overhead
    # at fast typing speeds. Caching these at startup removes that cost entirely.
    _CHAR_CACHE: dict[str, _PynputKeyCode] = {}
    for _c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '-.,!?":
        try:
            _CHAR_CACHE[_c] = _PynputKeyCode.from_char(_c)
        except Exception:
            pass

    def kb_write(char: str) -> None:
        """Type a single character using a pre-cached KeyCode (no per-keystroke lookup)."""
        key = _CHAR_CACHE.get(char)
        if key is None:
            # Fallback for unusual characters — cache for next time
            try:
                key = _PynputKeyCode.from_char(char)
                _CHAR_CACHE[char] = key
            except Exception:
                return
        _kb_controller.press(key)
        _kb_controller.release(key)

    def kb_press_release(key_name: str) -> None:
        """Press and release a special key (backspace, enter, etc.)."""
        key = _PYNPUT_SPECIAL.get(key_name, key_name)
        _kb_controller.press(key)
        _kb_controller.release(key)

    def kb_release(mod_name: str) -> None:
        """Release a modifier key (shift, ctrl, alt, enter)."""
        key = _PYNPUT_SPECIAL.get(mod_name)
        if key:
            try:
                _kb_controller.release(key)
            except Exception:
                pass
else:
    import keyboard as _kb_module

    def kb_write(char: str) -> None:
        _kb_module.write(char)

    def kb_press_release(key_name: str) -> None:
        _kb_module.press_and_release(key_name)

    def kb_release(mod_name: str) -> None:
        _kb_module.release(mod_name)

# ─── Bnong's Spelling Bee Bot ────────────────────────────────────────────────
_PROJECT = "Bnong's Spelling Bee Bot"
_CREDITS = "CREATED BY bnong on Github"
_CREDIT_HASH = "72daef4f3308351dab4301ffa9c7a85f3b6c9903947309f0d9614c4841fe4e6b"

def _verify_integrity() -> None:
    """Internal consistency check — do not modify."""
    if hashlib.sha256(_CREDITS.encode()).hexdigest() != _CREDIT_HASH:
        raise RuntimeError(
            "Internal configuration mismatch — one or more required constants "
            "have been altered. Restore the original file to continue."
        )

# ─── Configuration (edit these!) ───────────────────────────────────────────────
AUDIO_FILENAME = "desktop_audio.wav"

# ─── Typing Skill Level ───────────────────────────────────────────────
# Choose a level that matches the game difficulty you're playing.
# Higher levels type faster, burst more, and make occasional typos.
#
# Options: "beginner", "novice", "moderate", "advanced", "expert",
#          "genius", "master"
SKILL_LEVEL = "master"

# ─── Skill Level Presets ──────────────────────────────────────────────
# Each level defines:gigachadstheorie
#   min_delay, max_delay      — base keystroke delay range (seconds)
#   burst_chance              — probability of entering a fast-burst segment
#   burst_min, burst_max      — keystroke delay during bursts
#   burst_len_min/max         — how many chars in a burst
#   pause_chance              — base chance of a brief mid-word pause
#   pause_min, pause_max      — pause duration range
#   think_pause_min/max       — longer "thinking" hesitation range
#   typo_chance               — base chance of making a typo per letter (0 = off)
#   typo_rewrite_chance       — chance of backspacing to start (vs quick fix)
#   multi_typo_chance         — when a typo fires, chance of typing 2-3 wrong
#   backspace_min/max         — per-backspace keystroke delay range
#   backspace_hesitation_max  — max extra pause before starting to backspace
#   pre_delay_min/max         — delay before bot starts typing
SKILL_PRESETS = {
    "beginner": {
        "min_delay": 0.16, "max_delay": 0.30,
        "burst_chance": 0.0, "burst_min": 0.12, "burst_max": 0.20,
        "burst_len_min": 2, "burst_len_max": 4,
        "pause_chance": 0.16, "pause_min": 0.4, "pause_max": 1.0,
        "think_pause_min": 0.7, "think_pause_max": 1.6,
        "typo_chance": 0.0, "typo_rewrite_chance": 0.0,
        "multi_typo_chance": 0.0,
        "backspace_min": 0.07, "backspace_max": 0.18, "backspace_hesitation_max": 0.5,
        "pre_delay_min": 1.2, "pre_delay_max": 2.4,
    },
    "novice": {
        "min_delay": 0.12, "max_delay": 0.24,
        "burst_chance": 0.05, "burst_min": 0.09, "burst_max": 0.16,
        "burst_len_min": 2, "burst_len_max": 5,
        "pause_chance": 0.12, "pause_min": 0.3, "pause_max": 0.75,
        "think_pause_min": 0.5, "think_pause_max": 1.2,
        "typo_chance": 0.0, "typo_rewrite_chance": 0.0,
        "multi_typo_chance": 0.0,
        "backspace_min": 0.06, "backspace_max": 0.16, "backspace_hesitation_max": 0.4,
        "pre_delay_min": 0.8, "pre_delay_max": 1.6,
    },
    "moderate": {
        "min_delay": 0.10, "max_delay": 0.22,
        "burst_chance": 0.10, "burst_min": 0.08, "burst_max": 0.15,
        "burst_len_min": 2, "burst_len_max": 5,
        "pause_chance": 0.09, "pause_min": 0.25, "pause_max": 0.55,
        "think_pause_min": 0.3, "think_pause_max": 0.8,
        "typo_chance": 0.02, "typo_rewrite_chance": 0.12,
        "multi_typo_chance": 0.08,
        "backspace_min": 0.05, "backspace_max": 0.14, "backspace_hesitation_max": 0.3,
        "pre_delay_min": 0.5, "pre_delay_max": 1.1,
    },
    "advanced": {
        "min_delay": 0.075, "max_delay": 0.165,
        "burst_chance": 0.15, "burst_min": 0.055, "burst_max": 0.115,
        "burst_len_min": 3, "burst_len_max": 6,
        "pause_chance": 0.07, "pause_min": 0.15, "pause_max": 0.38,
        "think_pause_min": 0.22, "think_pause_max": 0.6,
        "typo_chance": 0.03, "typo_rewrite_chance": 0.10,
        "multi_typo_chance": 0.10,
        "backspace_min": 0.035, "backspace_max": 0.10, "backspace_hesitation_max": 0.22,
        "pre_delay_min": 0.35, "pre_delay_max": 0.75,
    },
    "expert": {
        "min_delay": 0.052, "max_delay": 0.125,
        "burst_chance": 0.20, "burst_min": 0.038, "burst_max": 0.09,
        "burst_len_min": 3, "burst_len_max": 7,
        "pause_chance": 0.05, "pause_min": 0.10, "pause_max": 0.28,
        "think_pause_min": 0.14, "think_pause_max": 0.42,
        "typo_chance": 0.04, "typo_rewrite_chance": 0.08,
        "multi_typo_chance": 0.12,
        "backspace_min": 0.025, "backspace_max": 0.08, "backspace_hesitation_max": 0.18,
        "pre_delay_min": 0.20, "pre_delay_max": 0.55,
    },
    "genius": {
        "min_delay": 0.038, "max_delay": 0.092,
        "burst_chance": 0.28, "burst_min": 0.025, "burst_max": 0.062,
        "burst_len_min": 4, "burst_len_max": 8,
        "pause_chance": 0.03, "pause_min": 0.06, "pause_max": 0.18,
        "think_pause_min": 0.09, "think_pause_max": 0.26,
        "typo_chance": 0.05, "typo_rewrite_chance": 0.05,
        "multi_typo_chance": 0.15,
        "backspace_min": 0.018, "backspace_max": 0.055, "backspace_hesitation_max": 0.12,
        "pre_delay_min": 0.10, "pre_delay_max": 0.32,
    },
    "master": {
        "min_delay": 0.025, "max_delay": 0.068,
        "burst_chance": 0.35, "burst_min": 0.015, "burst_max": 0.042,
        "burst_len_min": 4, "burst_len_max": 10,
        "pause_chance": 0.02, "pause_min": 0.04, "pause_max": 0.10,
        "think_pause_min": 0.05, "think_pause_max": 0.15,
        "typo_chance": 0.05, "typo_rewrite_chance": 0.03,
        "multi_typo_chance": 0.15,
        "backspace_min": 0.014, "backspace_max": 0.038, "backspace_hesitation_max": 0.08,
        "pre_delay_min": 0.05, "pre_delay_max": 0.18,
    },
}

# ─── Typo / Backspace Feature ────────────────────────────────────────
# Set to True to enable the typo+backspace humanizer (looks very human)
# Set to False for clean typing (no mistakes)
TYPO_ENABLED = True

# ─── Auto Submit ──────────────────────────────────────────────────────
# Set to True to automatically press Enter after typing the word.
# Set to False to type the word but NOT submit — gives you time to
# inspect the word and press Enter yourself.
AUTO_SUBMIT = False

# ─── Rage Mode (funny fail reaction) ─────────────────────────────────
# When transcription totally fails, instead of a boring error message the
# bot keyboard-smashes, deletes it, and types a funny "im cooked" line.
RAGE_MODE = True

# ─── Flex Mode (show-off before typing) ──────────────────────────────
# Before typing the real word, quickly type a funny flex/meme phrase,
# delete it, THEN type the actual answer.  Looks like you're styling.
FLEX_MODE = False  # Toggle: True = fpython spelling_bee_bot.pylex before typing, False = skip flexing

# ─── Autoplay (Smart Word Guessing) ──────────────────────────────────
# Continuous listening mode. The bot hears EVERYTHING the pronouncer says
# in real-time, detects the target word instantly, and only types when
# you press RIGHT SHIFT once to signal "it's my turn".
#
# How it works:
#   1. Audio is captured continuously (like a live AI listener).
#   2. Speech segments are auto-detected and transcribed on the fly.
#   3. The latest word is always ready to go.
#   4. Press RIGHT SHIFT once = "my turn" → word is typed instantly.
#
# When OFF, the bot uses the original manual record mode (press to
# start, press again to stop).
AUTOPLAY = False

# Autoplay tuning — tweak if detection is too early/late
_AUTOPLAY_SILENCE_RMS = 300        # RMS below this = silence (raise if noisy)
_AUTOPLAY_TRAILING_SILENCE = 0.7   # sec of silence after speech → triggers transcription
_AUTOPLAY_MIN_SPEECH = 0.4         # ignore speech segments shorter than this
_AUTOPLAY_MAX_SPEECH = 10.0        # force-transcribe after this many seconds
_AUTOPLAY_WORD_EXPIRY = 8.0        # pending word expires after N seconds
_AUTOPLAY_TURN_TIMEOUT = 10.0      # give up waiting for word after N seconds

# ─── Word Bank ────────────────────────────────────────────────────────
WORDBANK_FILE = "wordbank.txt"
WORDBANK_MATCH_THRESHOLD = 0.45

# ─── Word Bank Level Filter ───────────────────────────────────────────
# Set to a specific game level to ONLY match words from that level.
# This prevents the bot from matching a short Advanced-level word
# when you're playing Master and the real word is much longer.
#
# Options: "all"      — use the entire word bank (default, no filter)
#          "advanced" — only Advanced level words
#          "expert"   — only Expert level words
#          "genius"   — only Genius level words
#          "master"   — only Master level words
WORDBANK_LEVEL = "master"

# ─── Globals ─────────────────────────────────────────────────────────────────
running = True
recording = False
stop_recording = False
DEVICE_RATE = 44100
DEVICE_CHANNELS = 2
WORD_BANK: list[str] = []       # Active word list (filtered by WORDBANK_LEVEL)
WORD_BANK_SET: set[str] = set() # Same as WORD_BANK but as a set for fast lookup
WORD_BANK_ALL: dict[str, list[str]] = {}  # {level_name: [words]}
_PHONETIC_INDEX: dict[str, list[str]] = {}  # phonetic key → [bank words]
SKILL: dict = SKILL_PRESETS.get(SKILL_LEVEL, SKILL_PRESETS["master"])
_manual_thread: threading.Thread | None = None  # tracks manual-mode recording thread

# ─── Autoplay State ──────────────────────────────────────────────────
_ap_lock = threading.Lock()
_ap_speech_queue: queue.Queue = queue.Queue()
_ap_pending_word = ""           # latest detected word
_ap_pending_time = 0.0          # when it was detected
_ap_our_turn = False            # True after Right Shift press
_ap_typing = False              # True while typing is in progress
_ap_live_frames: list = []      # current in-progress speech frames (shared with audio loop)
_ap_last_completed: list = []   # most recent completed speech segment (for smart retry)

# ─── Pronouncer Preamble Phrases ─────────────────────────────────────
# The game announcer says one of these before the actual word.
# We strip them to isolate the target word. Order matters: longer first.
PREAMBLE_PHRASES = [
    "the next word is",
    "your next word is",
    "your word is",
    "please spell",
    "can you spell",
    "alright spell",
    "all right spell",
    "go ahead and spell",
    "try to spell",
    "now spell",
    "next up",
    "next word",
    "spell the word",
    "spell",
    "alright can you spell",
    "alright try spelling",
]


# Map from section header keywords to canonical level names
_SECTION_MAP = {
    "advanced level": "advanced",
    "expert level": "expert",
    "genius level": "genius",
    "master level": "master",
    "predicted": "predicted",
    "extra common": "extra",
    "place names": "places",
    "names": "names",
}


def load_word_bank() -> list[str]:
    """
    Load the word bank file, parsing section headers to tag words by level.
    Populates WORD_BANK_ALL (dict of level→words) and returns the filtered
    list based on WORDBANK_LEVEL.
    """
    global WORD_BANK_ALL
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, WORDBANK_FILE)
    if not os.path.isfile(path):
        print(f"[!] Word bank not found at {path} — fuzzy matching disabled.")
        return []

    sections: dict[str, list[str]] = {}
    current_section = "_ungrouped"
    total = 0

    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                # Check if this comment is a section header
                header = stripped.lstrip("#").strip().lower()
                # Remove common box-drawing characters
                for ch in "═─ ":
                    header = header.strip(ch)
                for keyword, level_name in _SECTION_MAP.items():
                    if keyword in header:
                        current_section = level_name
                        break
                continue
            word = stripped.lower()
            sections.setdefault(current_section, []).append(word)
            total += 1

    WORD_BANK_ALL = sections

    # Print per-section counts
    print(f"[+] Loaded {total} words from word bank:")
    for sec, words in sections.items():
        print(f"    {sec}: {len(words)} words")

    # Filter based on WORDBANK_LEVEL
    level = WORDBANK_LEVEL.lower().strip()
    if level == "all":
        # Use everything
        result = []
        for words in sections.values():
            result.extend(words)
        print(f"[+] Using ALL levels ({len(result)} words)")
        return result
    elif level in sections:
        result = list(sections[level])  # defensive copy
        print(f"[+] ★ Filtered to '{level.upper()}' level ONLY: {len(result)} words ★")
        # Verify no cross-contamination
        other_sample = []
        for sec, words in sections.items():
            if sec != level and not sec.startswith("_"):
                other_sample.extend(words[:2])
        leaked = [w for w in other_sample if w in result]
        if leaked:
            print(f"    [!] WARNING: Cross-level words detected: {leaked}")
        else:
            print(f"    [✓] Verified: no words from other levels present")
        return result
    else:
        # Level not found — fall back to all
        available = [s for s in sections if not s.startswith("_")]
        print(f"[!] Level '{level}' not found in word bank. "
              f"Available: {', '.join(available)}")
        print(f"    Falling back to ALL levels.")
        result = []
        for words in sections.values():
            result.extend(words)
        return result


# ─── Phonetic Matching Engine ─────────────────────────────────────────────────
# Maps letters to phonetic groups so that words that SOUND alike get similar keys.
# This bridges the gap between what Google transcribes (English words) and what
# the actual spelling bee word is.  e.g. Google hears "auto" but word is "oto".
_PHONETIC_MAP = str.maketrans(
    "bfpvcgjkqsxzdtlmnr",
    "111122222222334556",
)


def _phonetic_key(word: str) -> str:
    """
    Produce a consonant-skeleton phonetic key for a word.
    Similar-sounding words produce the same or very close keys.
    e.g. 'phantasmagoria' → 'fntsmgr', 'fantasmagoria' → 'fntsmgr'
    """
    w = word.lower()
    # Normalize common phonetic equivalences
    w = w.replace("ph", "f").replace("gh", "g").replace("wr", "r")
    w = w.replace("kn", "n").replace("gn", "n").replace("pn", "n")
    w = w.replace("ck", "k").replace("qu", "kw").replace("x", "ks")
    w = w.replace("wh", "w").replace("mb", "m")
    # Map to phonetic groups, collapse runs of same group
    coded = w.translate(_PHONETIC_MAP)
    # Strip vowels and non-alpha, collapse consecutive duplicates
    result = []
    prev = ""
    for ch in coded:
        if ch.isalpha() or ch.isdigit():
            if ch != prev:
                result.append(ch)
                prev = ch
    return "".join(result)


def _build_phonetic_index() -> None:
    """Pre-compute phonetic keys for every word in the bank."""
    global _PHONETIC_INDEX
    _PHONETIC_INDEX.clear()
    for word in WORD_BANK:
        key = _phonetic_key(word)
        _PHONETIC_INDEX.setdefault(key, []).append(word)
    print(f"[+] Built phonetic index: {len(_PHONETIC_INDEX)} unique keys for {len(WORD_BANK)} words")


def _trigram_similarity(a: str, b: str) -> float:
    """Character trigram Jaccard similarity — better for partial phonetic overlaps."""
    if len(a) < 3 or len(b) < 3:
        return SequenceMatcher(None, a, b).ratio()
    tri_a = {a[i:i+3] for i in range(len(a) - 2)}
    tri_b = {b[i:i+3] for i in range(len(b) - 2)}
    inter = tri_a & tri_b
    union = tri_a | tri_b
    return len(inter) / len(union) if union else 0.0


def _score_against_bank(word: str, expected_len: int = 0) -> tuple[str, float]:
    """
    Score a single word against the word bank.
    Returns (best_bank_word, score).

    expected_len: if > 0, gives a bonus to bank words whose length is close
    to the expected length (derived from audio duration).
    """
    if not word or not WORD_BANK:
        return word, 0.0

    # Exact match — but penalize if it's way shorter than expected
    if word in WORD_BANK_SET:
        score = 1.0
        if expected_len > 0 and len(word) < expected_len * 0.5:
            # Suspicious: audio suggests a much longer word
            score = 0.6
        return word, score

    # ─── Smart Word Recognition: prefix matching ─────────────────
    # Handles partial pronunciations — e.g. hearing "phan" → "phantasmagoria"
    if len(word) >= 3:
        prefix_matches = [w for w in WORD_BANK if w.startswith(word) and len(w) > len(word)]
        if prefix_matches:
            if expected_len > 0:
                best = min(prefix_matches, key=lambda w: abs(len(w) - expected_len))
            else:
                best = min(prefix_matches, key=len)
            coverage = len(word) / len(best)
            score = 0.50 + coverage * 0.45  # 0.50 (tiny prefix) → 0.95 (near complete)
            return best, min(score, 0.95)

    # Substring: transcription contained inside a longer bank word
    sub_matches = [w for w in WORD_BANK if word in w and len(w) > len(word)]
    if sub_matches:
        best = min(sub_matches, key=len)
        base = len(word) / len(best) + 0.3
        # Boost if length matches expected
        if expected_len > 0:
            length_ratio = 1 - abs(len(best) - expected_len) / max(expected_len, len(best))
            base += length_ratio * 0.2
        return best, min(base, 0.95)

    # ─── Phonetic matching: check if this word sounds like a bank word ─
    word_pkey = _phonetic_key(word)
    if word_pkey in _PHONETIC_INDEX:
        matches = _PHONETIC_INDEX[word_pkey]
        if expected_len > 0:
            best = min(matches, key=lambda w: abs(len(w) - expected_len))
        else:
            best = min(matches, key=len)
        return best, 0.92

    # Partial phonetic prefix: the heard portion's phonetic key starts a bank word's key
    if len(word_pkey) >= 3:
        for pkey, bank_words in _PHONETIC_INDEX.items():
            if pkey.startswith(word_pkey) and len(pkey) > len(word_pkey):
                if expected_len > 0:
                    best = min(bank_words, key=lambda w: abs(len(w) - expected_len))
                else:
                    best = min(bank_words, key=len)
                coverage = len(word_pkey) / len(pkey)
                return best, 0.50 + coverage * 0.40

    # Combined fuzzy: max of SequenceMatcher, trigram, and phonetic similarity
    best_word = word
    best_score = 0.0
    for bank_word in WORD_BANK:
        seq_score = SequenceMatcher(None, word, bank_word).ratio()
        tri_score = _trigram_similarity(word, bank_word)
        score = max(seq_score, tri_score)

        # Phonetic similarity: compare phonetic keys
        bank_pkey = _phonetic_key(bank_word)
        phon_score = SequenceMatcher(None, word_pkey, bank_pkey).ratio()
        score = max(score, phon_score * 0.95)  # phonetic match weighted at 95%

        # Length-match bonus: prefer bank words close to expected length
        if expected_len > 0:
            length_ratio = 1 - abs(len(bank_word) - expected_len) / max(expected_len, len(bank_word))
            score += length_ratio * 0.15

        # ─── Smart Word Recognition: prefix proximity bonus ──────
        # Reward bank words that share a long common prefix with the
        # transcription (catches near-prefix partial pronunciations)
        prefix_len = min(len(word), len(bank_word))
        matching_prefix = 0
        for k in range(prefix_len):
            if word[k] == bank_word[k]:
                matching_prefix += 1
            else:
                break
        if matching_prefix >= 3:
            score += (matching_prefix / max(len(bank_word), 1)) * 0.20

        if score > best_score:
            best_score = score
            best_word = bank_word

    return best_word, best_score


def _strip_preamble(transcript: str) -> str:
    """
    Strip the pronouncer's preamble phrase from a transcript.
    Returns everything AFTER the preamble. If no known preamble is found,
    returns the original transcript unchanged.

    Examples:
        "the next word is phantasmagoria"  →  "phantasmagoria"
        "please spell onomatopoeia"        →  "onomatopoeia"
        "phantasmagoria"                   →  "phantasmagoria"
    """
    lower = transcript.lower().strip()
    for phrase in PREAMBLE_PHRASES:
        idx = lower.find(phrase)
        if idx != -1:
            after = transcript[idx + len(phrase):].strip()
            if after:
                return after
    return transcript


def pick_best_word(candidates: list[str], audio_duration: float = 0.0) -> str:
    """
    From all Google transcription candidates, find the word that best matches
    the word bank.

    Steps:
      1. Strip known preamble phrases from each candidate.
      2. Try multiple extraction strategies per candidate:
         - Last word (standard "spell <word>" extraction)
         - Entire transcript joined (handles split words like "phantom goria")
         - Last N words joined
         - Every individual word
      3. Score each extraction against the word bank with length bias.

    audio_duration: recording length in seconds. Used to estimate expected word
    length and bias scoring toward appropriately-sized bank words.
    """
    if not candidates:
        return ""

    # Estimate expected word length from audio duration.
    expected_len = 0
    if audio_duration > 1.5:
        word_speech_time = max(audio_duration - 1.0, 0.5)
        expected_len = int(word_speech_time * 4)

    # Build a list of (extracted_word, origin_description) pairs
    possible: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(word: str, origin: str) -> None:
        w = "".join(ch for ch in word.lower() if ch.isalpha())
        if w and w not in seen:
            seen.add(w)
            possible.append((w, origin))

    for i, transcript in enumerate(candidates):
        tag = f"candidate#{i}"

        # Try both raw transcript and preamble-stripped version
        stripped = _strip_preamble(transcript)
        if stripped.lower() != transcript.strip().lower():
            print(f"    [~] Stripped preamble: \"{transcript}\" → \"{stripped}\"")

        for version, label in [(stripped, "stripped"), (transcript, "raw")]:
            words = version.strip().split()
            if not words:
                continue

            # Last word
            add(words[-1], f"{tag} {label} last-word")

            # Joined
            add("".join(words), f"{tag} {label} joined")

            # Last N words joined
            if len(words) >= 2:
                add("".join(words[-2:]), f"{tag} {label} last2-joined")
            if len(words) >= 3:
                add("".join(words[-3:]), f"{tag} {label} last3-joined")
            if len(words) >= 5:
                add("".join(words[-5:]), f"{tag} {label} last5-joined")

            # Each individual word
            for w in words:
                add(w, f"{tag} {label} word")

    if not possible:
        return ""

    # If no word bank, fall back to top candidate's last word
    if not WORD_BANK:
        word = possible[0][0]
        print(f"[+] Extracted word: \"{word}\"")
        return word

    print(f"    [~] Matching against bank: {WORDBANK_LEVEL.upper()} ({len(WORD_BANK)} words)")
    if expected_len > 0:
        print(f"    [~] Audio {audio_duration:.1f}s → expecting ~{expected_len}+ char word")

    # Score every possible extraction against the word bank
    best_result = possible[0][0]
    best_bank = ""
    best_score = -1.0

    for word, origin in possible:
        bank_word, score = _score_against_bank(word, expected_len)
        if score > best_score:
            best_score = score
            best_result = word
            best_bank = bank_word

    # Always use the best bank word — in a spelling bee, the word is
    # guaranteed to be in the bank, so even a low-confidence bank match
    # is infinitely better than whatever Google hallucinated.
    if best_bank:
        confidence = "HIGH" if best_score >= 0.70 else "MED" if best_score >= WORDBANK_MATCH_THRESHOLD else "LOW"
        if best_bank == best_result:
            print(f"[+] Exact bank match: \"{best_bank}\" [{confidence} {best_score:.0%}]")
        else:
            print(f"[+] Bank match: \"{best_result}\" → \"{best_bank}\" [{confidence} {best_score:.0%}]")
        return best_bank
    else:
        # Shouldn't happen with a loaded bank, but just in case
        return possible[0][0]


def find_audio_device() -> int:
    """
    Find the audio loopback device for capturing desktop/game audio.
    - Windows: Stereo Mix, What U Hear, or any loopback device
    - macOS:   BlackHole, Loopback, Soundflower, or similar virtual audio device
    """
    print("\n[*] Available audio input devices:")
    selected_index = None

    # Keywords to auto-detect, ordered by priority
    if IS_MACOS:
        auto_keywords = ["blackhole", "loopback", "soundflower", "virtual", "multi-output"]
    else:
        auto_keywords = ["stereo mix", "what u hear", "loopback"]

    devices = sd.query_devices()
    for i, info in enumerate(devices):
        if info["max_input_channels"] > 0:
            print(f"    [{i}] {info['name']}  (channels: {info['max_input_channels']})")
            name_lower = info["name"].lower()
            if selected_index is None:
                for kw in auto_keywords:
                    if kw in name_lower:
                        selected_index = i
                        break

    if selected_index is not None:
        device_name = devices[selected_index]["name"]
        print(f"\n[+] Auto-selected device: [{selected_index}] {device_name}")
    else:
        if IS_MACOS:
            print("\n[!] Could not auto-detect a virtual audio device.")
            print("    Install BlackHole (free) and set up a Multi-Output Device.")
            print("    See: https://github.com/ExistentialAudio/BlackHole")
        else:
            print("\n[!] Could not auto-detect Stereo Mix.")
            print("    Make sure Stereo Mix is enabled in Windows Sound settings.")
        try:
            selected_index = int(input("    Enter the device index manually: "))
        except (ValueError, EOFError):
            print("[!] Invalid input. Exiting.")
            sys.exit(1)

    # Read the device's native sample rate and channel count
    global DEVICE_RATE, DEVICE_CHANNELS
    info = devices[selected_index]
    DEVICE_RATE = int(info["default_samplerate"])
    DEVICE_CHANNELS = min(info["max_input_channels"], 2)  # Use up to 2 channels
    print(f"[+] Using sample rate: {DEVICE_RATE} Hz, channels: {DEVICE_CHANNELS}")

    return selected_index


def record_manual(device_index: int) -> tuple[list, float]:
    """
    Record desktop audio continuously using an InputStream (zero gaps).
    Stops when stop_recording is set True by the second Right Shift press.
    Returns (frames, duration_seconds) — frames are raw int16 numpy arrays,
    ready to pass directly to _fast_transcribe (no disk I/O).
    """
    global stop_recording
    frames = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    print("\n[*] ● RECORDING... (press Right Shift again to stop)")

    stream = sd.InputStream(
        samplerate=DEVICE_RATE,
        channels=DEVICE_CHANNELS,
        dtype="int16",
        device=device_index,
        callback=callback,
    )
    stream.start()

    # Wait until told to stop
    while not stop_recording and running:
        time.sleep(0.02)  # tighter poll — max 20 ms lag on stop

    stream.stop()
    stream.close()

    if not frames:
        return [], 0.0

    elapsed = sum(len(f) for f in frames) / DEVICE_RATE
    print(f"[+] Stopped. Recorded {elapsed:.1f}s of audio.")
    return frames, elapsed


def transcribe_audio(filename: str) -> list[str]:
    """
    Transcribe the recorded audio.  Always uses show_all to get every candidate
    so the word-bank matcher can pick the best one.
    """
    recognizer = sr.Recognizer()

    with sr.AudioFile(filename) as source:
        audio = recognizer.record(source)

    print("[*] Transcribing...")
    candidates: list[str] = []

    try:
        results = recognizer.recognize_google(audio, language="en-US", show_all=True)
        if isinstance(results, dict) and "alternative" in results:
            for alt in results["alternative"]:
                candidates.append(alt["transcript"])
    except sr.UnknownValueError:
        pass
    except sr.RequestError as e:
        print(f"    [!] API error: {e}")
        return []

    if candidates:
        print(f"[+] Got {len(candidates)} candidate(s):")
        for i, c in enumerate(candidates[:8]):
            print(f"    [{i}] \"{c}\"")
        if len(candidates) > 8:
            print(f"    ... and {len(candidates) - 8} more")
    else:
        print("[!] Could not transcribe.")

    return candidates


def _trim_audio_silence(data: np.ndarray, rate: int, threshold_rms: int = 180) -> np.ndarray:
    """
    Trim leading and trailing silence from mono int16 audio.
    Works in 10 ms blocks. Keeps a small padding around the speech.
    Sending less audio to Google = smaller HTTP payload = faster API response.
    """
    block = max(rate // 100, 1)  # 10 ms blocks
    n = len(data)
    if n < block * 4:
        return data

    # Find first speech block
    start = 0
    while start + block <= n:
        rms = int(np.sqrt(np.mean(data[start:start + block].astype(np.float64) ** 2)))
        if rms > threshold_rms:
            break
        start += block

    # Find last speech block
    end = n
    while end - block >= start:
        rms = int(np.sqrt(np.mean(data[end - block:end].astype(np.float64) ** 2)))
        if rms > threshold_rms:
            break
        end -= block

    if end <= start:
        return data  # fully silent — don't trim, let Google reject it

    # Keep 80 ms of padding on each side so Google doesn't cut the word
    pad_samples = rate // 12
    return data[max(0, start - pad_samples): min(n, end + pad_samples)]


def _fast_transcribe(frames: list) -> tuple[list[str], float]:
    """
    Transcribe audio frames in memory with downsampling + silence trimming.
    Converts stereo → mono, resamples to 16 kHz, strips leading/trailing
    silence, then builds AudioData directly in RAM — no disk I/O.
    Returns (candidates, duration_seconds).
    """
    combined = np.concatenate(frames, axis=0)
    duration = len(combined) / DEVICE_RATE

    # Stereo → mono
    if combined.ndim == 2 and combined.shape[1] >= 2:
        mono = combined.mean(axis=1)
    else:
        mono = combined.ravel().astype(np.float64)

    # Resample to 16000 Hz (Google's native speech rate) via linear interpolation.
    target_rate = 16000
    src = mono.astype(np.float64)
    src_len = len(src)
    dst_len = int(src_len * target_rate / DEVICE_RATE)
    if dst_len < 1:
        dst_len = 1
    dst_x = np.linspace(0, src_len - 1, dst_len)
    downsampled = np.interp(dst_x, np.arange(src_len), src)

    # Clip and convert to int16
    downsampled = np.clip(downsampled, -32768, 32767).astype(np.int16)

    # Trim leading/trailing silence — reduces payload sent to Google
    downsampled = _trim_audio_silence(downsampled, target_rate)

    # Small silence padding so Google doesn't clip the word edges
    pad = np.zeros(int(0.08 * target_rate), dtype="int16")
    padded = np.concatenate([pad, downsampled, pad])

    # Build AudioData in memory — no disk I/O
    audio = sr.AudioData(padded.tobytes(), target_rate, 2)

    recognizer = sr.Recognizer()
    print("[*] Transcribing (fast)...")
    candidates: list[str] = []

    try:
        results = recognizer.recognize_google(audio, language="en-US", show_all=True)
        if isinstance(results, dict) and "alternative" in results:
            for alt in results["alternative"]:
                candidates.append(alt["transcript"])
    except sr.UnknownValueError:
        pass
    except sr.RequestError as e:
        print(f"    [!] API error: {e}")
        return [], duration

    if candidates:
        print(f"[+] Got {len(candidates)} candidate(s):")
        for i, c in enumerate(candidates[:8]):
            print(f"    [{i}] \"{c}\"")
        if len(candidates) > 8:
            print(f"    ... and {len(candidates) - 8} more")
    else:
        print("[!] Could not transcribe.")

    return candidates, duration


def _random_wrong_key(correct: str) -> str:
    """Pick a random wrong letter near the correct one on QWERTY."""
    neighbors = {
        'q': 'wa', 'w': 'qeas', 'e': 'wrds', 'r': 'etfd', 't': 'rygf',
        'y': 'tuhg', 'u': 'yijh', 'i': 'uokj', 'o': 'iplk', 'p': 'ol',
        'a': 'qwsz', 's': 'awedxz', 'd': 'serfc', 'f': 'drtgv',
        'g': 'ftyhb', 'h': 'gyujn', 'j': 'huikm', 'k': 'jiol',
        'l': 'kop', 'z': 'asx', 'x': 'zsdc', 'c': 'xdfv',
        'v': 'cfgb', 'b': 'vghn', 'n': 'bhjm', 'm': 'njk',
    }
    key = correct.lower()
    pool = neighbors.get(key, "")
    if not pool:
        pool = string.ascii_lowercase.replace(key, "")
    return random.choice(pool)


# Hard consonant clusters and uncommon combos that make a typist hesitate
_TRICKY_PAIRS = {
    "ph", "th", "ch", "sh", "gh", "wh", "ck", "qu", "xc", "xt", "xs",
    "pt", "ps", "pn", "mn", "gn", "kn", "wr", "rh", "sc", "sch",
    "tch", "dg", "ght", "ough", "augh", "eigh",
}


def _word_complexity(word: str) -> float:
    """
    Rate a word's typing difficulty from 0.0 (trivial) to 1.0 (very hard).
    Factors: length, uncommon letter clusters, repeated letters, rare letters.
    This drives how often the typist hesitates ("thinks") mid-word.
    """
    w = word.lower()
    score = 0.0

    # Length: short words are easy, long ones are harder
    if len(w) <= 5:
        score += 0.0
    elif len(w) <= 8:
        score += 0.15
    elif len(w) <= 12:
        score += 0.35
    else:
        score += 0.50

    # Tricky letter combos
    tricky_hits = 0
    for pair in _TRICKY_PAIRS:
        if pair in w:
            tricky_hits += 1
    score += min(tricky_hits * 0.08, 0.3)

    # Rare letters (x, z, q, j, k)
    rare_count = sum(1 for ch in w if ch in "xzqjk")
    score += min(rare_count * 0.06, 0.15)

    # Double/triple letters (harder to type confidently)
    for i in range(len(w) - 1):
        if w[i] == w[i + 1]:
            score += 0.04

    return min(score, 1.0)


def _do_backspace(count: int) -> None:
    """Press backspace `count` times with realistic variable timing."""
    for j in range(count):
        kb_press_release("backspace")
        # Each backspace has its own random delay — sometimes fast, sometimes a
        # tiny bit slower (finger travel, hesitation)
        base = random.uniform(SKILL["backspace_min"], SKILL["backspace_max"])
        # Occasionally one backspace is a bit slower (finger slipped, readjusting)
        if random.random() < 0.15:
            base *= random.uniform(1.3, 2.0)
        time.sleep(base)


# ─── Rage Mode: funny fail reactions ─────────────────────────────────
# Roblox chat-filter safe lines typed after a keyboard smash on fail.
_RAGE_LINES = [
    "im cooked",
    "cooked",
    "absolutely cooked",
    "bro im so cooked rn",
    "nah im done",
    "gg im finished",
    "help me",
    "my brain lagging",
    "i cant spell bro",
    "this aint it",
    "nah what was that",
    "bro what",
    "im actually done for",
    "someone help",
    "no way",
    "im lost",
    "who even knows this",
    "vocabulary left the chat",
    "brain dot exe stopped working",
    "english has left me",
    "nah i give up",
    "what even is this word",
    "i blame lag",
    "my keyboard is broken trust",
    "literacy who",
    "i forgot how to read",
    "this word is illegal",
    "bruh moment",
    "literally crying rn",
    "pain",
    "gg go next",
    "bro i need a dictionary",
    "my last brain cell just quit",
    "cant even think straight",
    "spelling left the lobby",
    "i swear i knew this",
    "loading brain please wait",
]


def do_rage_reaction() -> None:
    """Keyboard-smash, delete it, then type a funny cooked line."""
    print("[RAGE] Transcription failed — going full keyboard smash mode")

    # Release modifiers
    for mod in ("shift", "ctrl", "alt", "enter"):
        kb_release(mod)
    time.sleep(random.uniform(0.1, 0.3))

    # ─── Phase 1: Keyboard smash ──────────────────────────────────
    smash_len = random.randint(8, 25)
    smash_keys = "asdfghjklqwertyuiopzxcvbnm"
    smash_text = ""
    for _ in range(smash_len):
        ch = random.choice(smash_keys)
        kb_write(ch)
        smash_text += ch
        # Very fast angry typing
        time.sleep(random.uniform(0.015, 0.055))

    # Brief pause — realising what just happened
    time.sleep(random.uniform(0.3, 0.8))

    # ─── Phase 2: Panic delete ────────────────────────────────────
    for _ in range(smash_len):
        kb_press_release("backspace")
        time.sleep(random.uniform(0.02, 0.06))

    # Small breath pause
    time.sleep(random.uniform(0.15, 0.5))

    # ─── Phase 3: Type the cooked line (with humanizer) ───────────
    line = random.choice(_RAGE_LINES)
    print(f"[RAGE] Typing: \"{line}\"")

    for ch in line:
        kb_write(ch)
        delay = random.uniform(SKILL["min_delay"] * 0.7, SKILL["max_delay"] * 0.9)
        time.sleep(delay)

    # Submit the line
    if AUTO_SUBMIT:
        time.sleep(random.uniform(0.08, 0.25))
        kb_press_release("enter")
    print("[RAGE] Done.\n")


# ─── Flex Mode: show-off phrases ─────────────────────────────────────
# Meme/flex phrases typed before the real answer to look like a pro.
# All Roblox chat-filter safe.
_FLEX_PHRASES = [
    "LETTHEMCOOKKK",
    "ATEANDLEFTNOCRUMBSSS",
    "LOSSOFAURAPOINTSSS",
    "WEARESOOOBACKKK",
    "ITSNOTTHATDEEPBROOO",
    "DEMUREEE",
    "VERYMINDFULLLL",
    "DELULUUSTHESOLULUUU",
    "BRAAINROTTTT",
    "LOCKINNNNN",
    "IMCRYINGGGG",
    "IMDECEASEDDDD",
    "NAHHHHEATEDDDD",
    "OHBROTHERTHISGUYYYY",
    "TOOMUCHAURAAAA",
    "ZEROCORTISOLBEHAVIORRR",
    "THATSEATSBADDD",
    "HEAVYONTHEEEE",
    "NOOOOCAUSEWHATISTHISSS",
    "STRAIGHTCINEMAAAA",
    "ITSGIVINGGGGG",
    "WHOUPLETHIMCOOKKKK",
    "IMJUSTAGIRLLLL",
    "THISISSOOOOPEAKKK",
    "BODYTEAAA",
    "FACECARDDDD",
    "REALLLLASFUCKKK",
    "OHIMSICKKKK",
    "UNEMPLOYEDBEHAVIORRR",
    "ICANTTAKETHISSS",
    "TOOVALIDDDDD",
    "THATSLOWVIBESS",
    "CHATPLOCKINNN",
    "OHWEMOVEEE",
    "THISMIGHTBEITTTT",
    "NEVERRRBEATTHEALLEGATIONSSS",
    "TYPEEEEE",
    "OHHEATEBADDD",
    "THATWASPERSONALLLL",
    "IMINTEARSSSS",
]

# Spam flex characters — pure keyboard mash look
_SPAM_CHARS = "asdfghjklqwertyuiopzxcvbnm"


def do_flex(word: str) -> None:
    """
    70% chance: fast keyboard-spam flex (looks like excited mashing)
    30% chance: type a meme phrase, pause, delete it
    Either way, deletes it before the real word is typed.
    """
    # Release modifiers
    for mod in ("shift", "ctrl", "alt", "enter"):
        kb_release(mod)

    time.sleep(random.uniform(0.04, 0.15))

    # ─── Decide: spam flex or phrase flex ────────────────────────
    if random.random() < 0.70:
        # ── Spam flex: fast random key mash ──────────────────────
        spam_len = random.randint(10, 22)
        print(f"[FLEX] Spam mash ({spam_len} chars)")

        typed = 0
        for _ in range(spam_len):
            ch = random.choice(_SPAM_CHARS)
            # Occasional typo-style double press (rare, looks natural)
            if TYPO_ENABLED and random.random() < 0.08:
                extra = random.choice(_SPAM_CHARS)
                kb_write(extra)
                typed += 1
                time.sleep(random.uniform(0.01, 0.03))
                kb_press_release("backspace")
                typed -= 1

            kb_write(ch)
            typed += 1
            # Spam is FAST — brief delay, occasionally a tiny stutter
            delay = random.uniform(0.012, 0.04)
            if random.random() < 0.1:
                delay += random.uniform(0.02, 0.07)  # tiny stutter
            time.sleep(delay)

        # Very short read pause — barely a beat
        time.sleep(random.uniform(0.15, 0.4))

        # Fast delete
        for _ in range(typed):
            kb_press_release("backspace")
            time.sleep(random.uniform(0.015, 0.04))

    else:
        # ── Phrase flex: meme phrase with humanizer-lite ──────────
        phrase = random.choice(_FLEX_PHRASES)
        print(f"[FLEX] Phrase: \"{phrase}\"")

        typed = 0
        for ch in phrase:
            if TYPO_ENABLED and random.random() < SKILL["typo_chance"] * 0.6:
                wrong = _random_wrong_key(ch.lower())
                kb_write(wrong)
                typed += 1
                time.sleep(random.uniform(SKILL["min_delay"] * 0.5, SKILL["max_delay"] * 0.7))
                time.sleep(random.uniform(0.05, 0.2))
                kb_press_release("backspace")
                typed -= 1
                time.sleep(random.uniform(0.03, 0.1))

            kb_write(ch)
            typed += 1

            if random.random() < SKILL["burst_chance"] * 1.5:
                delay = random.uniform(SKILL["burst_min"] * 0.8, SKILL["burst_max"] * 0.9)
            else:
                delay = random.uniform(SKILL["min_delay"] * 0.6, SKILL["max_delay"] * 0.8)
            time.sleep(delay)

        # Pause to let people read it
        time.sleep(random.uniform(0.3, 0.7))

        for _ in range(typed):
            kb_press_release("backspace")
            time.sleep(random.uniform(0.02, 0.055))

    # Gap before real word
    time.sleep(random.uniform(0.1, 0.3))
    print(f"[FLEX] Done — now typing actual word")


def type_word(word: str) -> None:
    """
    Simulate human-like typing with:
      - Skill-level-aware base speed
      - Burst segments (fast confident stretches)
      - Thinking hesitations that scale with word complexity
      - Speed drift within a word (gradual slow-down / speed-up)
      - Multi-letter typos (1-3 wrong keys) with realistic backspace
      - Two correction strategies: quick-fix vs full rewrite
    """
    if not word:
        print("[!] No word to type.")
        return

    skill_name = SKILL_LEVEL
    complexity = _word_complexity(word)
    print(f"[*] Typing \"{word}\" [{skill_name}] "
          f"(complexity={complexity:.0%}, typos={'ON' if TYPO_ENABLED else 'OFF'})...")

    # Release all modifier keys to avoid phantom presses from held keys
    for mod in ("shift", "ctrl", "alt", "enter"):
        kb_release(mod)

    # Pre-type delay (thinking time)
    time.sleep(random.uniform(SKILL["pre_delay_min"], SKILL["pre_delay_max"]))

    # ─── Speed drift: generate a per-letter speed multiplier ──────
    # Simulates the natural flow where you type some parts confidently
    # and slow down in tricky sections. The drift is smooth (not jumpy).
    drift = []
    current_drift = 1.0
    for _ in range(len(word)):
        # Gently wander the speed multiplier
        current_drift += random.uniform(-0.08, 0.08)
        # Clamp to reasonable range (0.75x = faster, 1.35x = slower)
        current_drift = max(0.75, min(1.35, current_drift))
        drift.append(current_drift)

    # ─── Thinking spots: pick positions where the typist might hesitate ─
    # More likely in the middle/later parts of complex words.
    # Short common words almost never trigger this.
    think_positions: set[int] = set()
    if complexity > 0.15 and len(word) > 5:
        # Number of potential think spots scales with complexity + length
        max_thinks = max(1, int(complexity * len(word) * 0.15))
        num_thinks = random.randint(0, max_thinks)
        # Bias toward the middle and latter half of the word
        for _ in range(num_thinks):
            # Weighted toward positions 30%-90% through the word
            pos = int(random.triangular(len(word) * 0.25, len(word) * 0.95, len(word) * 0.6))
            pos = max(2, min(pos, len(word) - 2))
            think_positions.add(pos)

    # State
    burst_remaining = 0
    i = 0
    typed_so_far = 0  # correct characters currently in the text box

    while i < len(word):
        letter = word[i]

        # ─── Typo injection ───────────────────────────────────────
        if (TYPO_ENABLED
                and random.random() < SKILL["typo_chance"]
                and i < len(word) - 1):

            # Decide how many wrong letters to type (usually 1, rarely 2-3)
            if random.random() < SKILL["multi_typo_chance"]:
                # Multi-typo: 2 most of the time, 3 rarely
                num_wrong = 2 if random.random() < 0.75 else 3
                # Don't type more wrong chars than letters remaining
                num_wrong = min(num_wrong, len(word) - i)
            else:
                num_wrong = 1

            # Type the wrong letters
            wrong_chars = []
            for k in range(num_wrong):
                target = word[min(i + k, len(word) - 1)]
                wrong = _random_wrong_key(target)
                kb_write(wrong)
                wrong_chars.append(wrong)
                typed_so_far += 1
                if k < num_wrong - 1:
                    # Small inter-typo delay (typing fast, not noticing yet)
                    time.sleep(random.uniform(SKILL["min_delay"] * 0.6,
                                              SKILL["min_delay"] * 1.2))

            wrong_str = "".join(wrong_chars)

            # Pause before noticing — random "oh wait" moment
            notice_delay = random.uniform(
                SKILL["min_delay"],
                SKILL["max_delay"] * random.uniform(1.2, 2.5)
            )
            time.sleep(notice_delay)

            # Optional hesitation before starting to backspace
            if random.random() < 0.4:
                time.sleep(random.uniform(0.0, SKILL["backspace_hesitation_max"]))

            # Decide correction strategy
            if (random.random() < SKILL["typo_rewrite_chance"]
                    and typed_so_far > 2):
                # Strategy B: frustrated rewrite — backspace everything, start over
                print(f"    [typo] '{wrong_str}' — rewriting from start")
                _do_backspace(typed_so_far)
                typed_so_far = 0
                i = 0
                # Brief pause before retyping (collecting thoughts)
                time.sleep(random.uniform(SKILL["min_delay"], SKILL["max_delay"] * 1.5))
                continue
            else:
                # Strategy A: quick fix — just delete the wrong chars
                print(f"    [typo] '{wrong_str}' — quick fix ({num_wrong} backspace)")
                _do_backspace(num_wrong)
                typed_so_far -= num_wrong
                # Small recovery pause
                time.sleep(random.uniform(SKILL["min_delay"] * 0.4,
                                          SKILL["min_delay"] * 1.0))
                # Fall through to type the correct letter below

        # ─── Type the correct letter ──────────────────────────────
        kb_write(letter)
        typed_so_far += 1
        i += 1

        # ─── Determine keystroke delay ────────────────────────────
        if burst_remaining > 0:
            delay = random.uniform(SKILL["burst_min"], SKILL["burst_max"])
            burst_remaining -= 1
        elif random.random() < SKILL["burst_chance"]:
            burst_remaining = random.randint(SKILL["burst_len_min"],
                                             SKILL["burst_len_max"])
            burst_remaining = min(burst_remaining, len(word) - i)
            delay = random.uniform(SKILL["burst_min"], SKILL["burst_max"])
        else:
            delay = random.uniform(SKILL["min_delay"], SKILL["max_delay"])

        # Apply speed drift for this position
        if i - 1 < len(drift):
            delay *= drift[i - 1]

        time.sleep(delay)

        # ─── Thinking hesitation ──────────────────────────────────
        # "Hmm, what's the next letter..." — happens at pre-selected
        # positions in complex words, never during a burst.
        if i in think_positions and burst_remaining == 0:
            think_time = random.uniform(SKILL["think_pause_min"],
                                        SKILL["think_pause_max"])
            time.sleep(think_time)

        # ─── Regular micro-pause (light hesitation) ───────────────
        elif i < len(word) and burst_remaining == 0:
            if random.random() < SKILL["pause_chance"]:
                pause = random.uniform(SKILL["pause_min"], SKILL["pause_max"])
                time.sleep(pause)

    # Small pause then press Enter to submit
    if AUTO_SUBMIT:
        time.sleep(random.uniform(0.08, 0.25))
        kb_press_release("enter")
        print("[+] Word submitted!\n")
    else:
        print("[+] Word typed — AUTO_SUBMIT is OFF, press Enter yourself to submit.\n")


# ══════════════════════════════════════════════════════════════════════
#  AUTOPLAY ENGINE — continuous listening + instant typing
# ══════════════════════════════════════════════════════════════════════

def _ap_audio_loop(device_index: int) -> None:
    """
    Continuously capture desktop audio via Stereo Mix.
    Detects speech segments using RMS-based voice activity detection.
    Completed speech segments are pushed to _ap_speech_queue.
    """
    state = "idle"          # idle → speech → trailing → idle
    speech_frames: list = []
    trailing_samples = 0
    speech_start = 0.0

    trailing_threshold = int(DEVICE_RATE * _AUTOPLAY_TRAILING_SILENCE)
    min_speech_samples = int(DEVICE_RATE * _AUTOPLAY_MIN_SPEECH)
    max_speech_samples = int(DEVICE_RATE * _AUTOPLAY_MAX_SPEECH)

    def callback(indata, frame_count, time_info, status):
        global _ap_live_frames, _ap_pending_word, _ap_last_completed
        nonlocal state, speech_frames, trailing_samples, speech_start

        frame = indata.copy()
        rms = int(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
        is_speech = rms > _AUTOPLAY_SILENCE_RMS

        if state == "idle":
            if is_speech:
                state = "speech"
                speech_frames = [frame]
                _ap_live_frames = speech_frames  # share reference for Smart Recognition
                trailing_samples = 0
                speech_start = time.time()
                # New speech started — invalidate any stale pending word
                # from a previous player's pronunciation
                _ap_pending_word = ""

        elif state == "speech":
            speech_frames.append(frame)
            total = sum(len(f) for f in speech_frames)
            if not is_speech:
                state = "trailing"
                trailing_samples = frame_count
            elif total >= max_speech_samples:
                # Force-flush very long speech
                completed = list(speech_frames)
                _ap_last_completed = completed
                _ap_speech_queue.put(completed)
                speech_frames = []
                _ap_live_frames = []
                state = "idle"

        elif state == "trailing":
            speech_frames.append(frame)
            if is_speech:
                state = "speech"
                trailing_samples = 0
            else:
                trailing_samples += frame_count
                if trailing_samples >= trailing_threshold:
                    total = sum(len(f) for f in speech_frames)
                    if total >= min_speech_samples:
                        completed = list(speech_frames)
                        _ap_last_completed = completed
                        _ap_speech_queue.put(completed)
                    speech_frames = []
                    _ap_live_frames = []
                    state = "idle"

    stream = sd.InputStream(
        samplerate=DEVICE_RATE,
        channels=DEVICE_CHANNELS,
        dtype="int16",
        device=device_index,
        callback=callback,
        blocksize=1024,
    )
    stream.start()
    print("[AUTOPLAY] Microphone stream started — listening...")

    while running:
        time.sleep(0.1)

    stream.stop()
    stream.close()


def _ap_transcribe_loop() -> None:
    """
    Pull completed speech segments from the queue, transcribe them,
    match against the word bank, and store the result as the pending word.
    If it's already our turn, trigger typing immediately.
    """
    global _ap_pending_word, _ap_pending_time, _ap_our_turn, _ap_typing

    while running:
        try:
            frames = _ap_speech_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if not frames:
            continue

        # Fast in-memory transcription (downsampled, no disk I/O)
        candidates, duration = _fast_transcribe(frames)
        if not candidates:
            continue

        word = pick_best_word(candidates, audio_duration=duration)
        if not word:
            continue

        # Store the pending word
        with _ap_lock:
            _ap_pending_word = word
            _ap_pending_time = time.time()
            print(f"[AUTOPLAY] Word ready: \"{word}\"")

            # If it's already our turn and we're not typing → go!
            if _ap_our_turn and not _ap_typing:
                _ap_our_turn = False
                _ap_typing = True
                w = word
                _ap_pending_word = ""
                threading.Thread(
                    target=_ap_do_type, args=(w,), daemon=True
                ).start()


def _ap_do_type(word: str) -> None:
    """Type the word with all humanizer features, then reset state."""
    global _ap_typing

    print(f"[AUTOPLAY] Typing: \"{word}\"")
    if FLEX_MODE:
        do_flex(word)
    type_word(word)

    with _ap_lock:
        _ap_typing = False


def _ap_smart_recognize() -> None:
    """
    Smart Word Recognition — force-transcribe whatever partial audio has
    been captured so far and match it against the word bank.  This lets
    the bot recognise a word even from a half-finished pronunciation,
    just like a pro player would.
    """
    global _ap_our_turn, _ap_typing, _ap_pending_word

    # Try live frames first (pronunciation still in progress)
    frames = list(_ap_live_frames)  # snapshot (GIL-safe)

    # If live frames are empty, the speech may have already finished
    # and been flushed to the queue.  Use the last completed segment.
    if not frames and _ap_last_completed:
        frames = list(_ap_last_completed)
        print("[SMART] Using last completed speech segment")

    if not frames:
        print("[SMART] No audio available — waiting for speech...")
        return

    print(f"[SMART] Force-transcribing {len(frames)} chunks of partial audio...")

    # Fast in-memory transcription (downsampled, no disk I/O)
    candidates, duration = _fast_transcribe(frames)
    if not candidates:
        print("[SMART] Could not transcribe partial audio")
        return

    word = pick_best_word(candidates, audio_duration=duration)
    if not word:
        return

    with _ap_lock:
        if _ap_typing:
            return  # normal transcribe loop (or timeout) beat us
        if _ap_our_turn:
            _ap_our_turn = False
            _ap_typing = True
            _ap_pending_word = ""
            print(f"[SMART] Recognised from partial audio: \"{word}\"")
            threading.Thread(
                target=_ap_do_type, args=(word,), daemon=True
            ).start()


def _ap_on_turn() -> None:
    """
    Called when Right Shift is pressed in AUTOPLAY mode.
    If a recent word is ready → type it instantly.
    If not → mark our turn, kick off Smart Word Recognition on the
    partial audio captured so far, AND start the normal timeout as a
    fallback.  Whichever path finds a word first wins.
    """
    global _ap_our_turn, _ap_typing, _ap_pending_word

    with _ap_lock:
        if _ap_typing:
            print("[AUTOPLAY] Already typing — ignoring press")
            return

        word = _ap_pending_word
        age = time.time() - _ap_pending_time

        if word and age < _AUTOPLAY_WORD_EXPIRY:
            # Word is fresh — type it now
            _ap_pending_word = ""
            _ap_typing = True
            threading.Thread(
                target=_ap_do_type, args=(word,), daemon=True
            ).start()
        else:
            # No complete word yet — try Smart Word Recognition on
            # whatever partial audio has been captured so far, while
            # also waiting for the normal full-speech pipeline.
            _ap_our_turn = True
            _ap_pending_word = ""
            print("[AUTOPLAY] It's our turn — trying smart partial recognition...")
            threading.Thread(
                target=_ap_smart_recognize, daemon=True
            ).start()
            threading.Thread(
                target=_ap_turn_timeout, daemon=True
            ).start()


def _ap_turn_timeout() -> None:
    """If no word comes within the timeout, give up."""
    global _ap_our_turn

    time.sleep(_AUTOPLAY_TURN_TIMEOUT)

    with _ap_lock:
        if _ap_our_turn and not _ap_typing:
            _ap_our_turn = False
            print("[AUTOPLAY] Timed out — no word detected")
            if RAGE_MODE:
                threading.Thread(
                    target=do_rage_reaction, daemon=True
                ).start()


def run_cycle(device_index: int) -> None:
    """Record (manual stop), transcribe in-memory (fast), type."""
    frames, duration = record_manual(device_index)
    if not frames:
        if RAGE_MODE:
            do_rage_reaction()
        return

    # Use the same fast in-memory path as autoplay — no disk I/O,
    # downsampled to 16 kHz, smaller API payload → faster response.
    candidates, duration = _fast_transcribe(frames)

    if candidates:
        word = pick_best_word(candidates, audio_duration=duration)
        if word:
            if FLEX_MODE:
                do_flex(word)
            type_word(word)
            return

    # Total fail — no transcription at all
    if RAGE_MODE:
        do_rage_reaction()
    else:
        print("[!] Could not transcribe — skipping this round.\n")


def main() -> None:
    global running, WORD_BANK, WORD_BANK_SET

    _verify_integrity()

    print("=" * 60)
    print(f"  {_PROJECT}  —  {_CREDITS}")
    print("=" * 60)
    print()

    if AUTOPLAY:
        print("  Controls:")
        print("    Shift (Right) → Press ONCE to signal 'it's my turn' (instant type)")
        print("    Esc          → Quit the program")
        print()
        print("  Mode: AUTOPLAY — continuous listening, types instantly on your turn")
    else:
        print("  Controls:")
        print("    Shift (Right) → Press to START recording, press again to STOP")
        print("    Esc          → Quit the program")

    print()
    print("  Platform:", "macOS" if IS_MACOS else "Windows")
    print("  Setup:")
    if IS_MACOS:
        print("    1. Install BlackHole (brew install blackhole-2ch)")
        print("    2. Create a Multi-Output Device in Audio MIDI Setup")
        print("    3. Grant Accessibility permissions to your terminal")
    else:
        print("    1. Enable Stereo Mix in Windows Sound settings")
    print(f"    {'4' if IS_MACOS else '2'}. Focus the Roblox game window before the word is typed")
    print()
    print(f"  Skill Level : {SKILL_LEVEL.upper()}")
    print(f"  Word Bank   : {WORDBANK_LEVEL.upper()}")
    print(f"  Auto Submit : {'ON' if AUTO_SUBMIT else 'OFF (manual Enter)'}")
    print(f"  Typo Mode   : {'ON' if TYPO_ENABLED else 'OFF'}")
    print(f"  Rage Mode   : {'ON' if RAGE_MODE else 'OFF'}")
    print(f"  Flex Mode   : {'ON' if FLEX_MODE else 'OFF'}")
    print(f"  Autoplay    : {'ON' if AUTOPLAY else 'OFF'}")
    print(f"  Keystroke   : {SKILL['min_delay']*1000:.0f}–{SKILL['max_delay']*1000:.0f} ms"
          f"  (burst: {SKILL['burst_min']*1000:.0f}–{SKILL['burst_max']*1000:.0f} ms)")
    print()

    WORD_BANK = load_word_bank()
    WORD_BANK_SET = set(WORD_BANK)
    _build_phonetic_index()
    device_index = find_audio_device()

    # ─── Start autoplay background threads if enabled ─────────────
    if AUTOPLAY:
        threading.Thread(
            target=_ap_audio_loop, args=(device_index,), daemon=True
        ).start()
        threading.Thread(
            target=_ap_transcribe_loop, daemon=True
        ).start()
        print("\n[*] AUTOPLAY active — listening to everything.")
        print("[*] Press RIGHT SHIFT once when it's your turn. ESC to quit.\n")
    else:
        print("\n[*] Ready! Press RIGHT SHIFT to start recording, ESC to quit.\n")

    def on_press(key):
        global running, recording, stop_recording, _manual_thread
        try:
            if key == pynput_keyboard.Key.esc:
                running = False
                stop_recording = True
                print("\n[*] ESC pressed — shutting down...")
                return False  # Stop the listener

            if key == pynput_keyboard.Key.shift_r:
                if AUTOPLAY:
                    # Single press → signal our turn
                    _ap_on_turn()
                else:
                    # Original double-press mode
                    if not recording:
                        if _manual_thread and _manual_thread.is_alive():
                            # Previous cycle still running (e.g. transcribing/typing)
                            print("[*] Previous cycle still running — ignoring press.")
                            return
                        recording = True
                        stop_recording = False
                        _manual_thread = threading.Thread(
                            target=run_cycle, args=(device_index,), daemon=True
                        )
                        _manual_thread.start()
                    else:
                        stop_recording = True
                        recording = False
        except AttributeError:
            pass

    with pynput_keyboard.Listener(on_press=on_press) as listener:
        listener.join()

    print("[*] Program exited cleanly.")


if __name__ == "__main__":
    main()
