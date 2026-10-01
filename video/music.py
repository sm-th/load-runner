"""Soundtrack of the load-runner presentation video, synthesized from scratch as an NES-style chiptune.

Four 2A03-like voices at 150 BPM (bar = 1.6 s): pulse 1 lead (left), pulse 2 harmony/echo (right),
a 4-bit stepped triangle bass and a noise-channel kit, plus a little room reverb. All tunes are original.
Cue map: 0 C-major "game start" jingle, vamp, pickup | 6.4 theme A, bouncy C major | 20.8 theme B,
A-minor cartoon chase with chromatic runs | 30.4 development in D minor, climb | 41.6 sixteenth-note chase;
45.6 the run fails (cut, slide whistle, poof at 46.4, pickup at 47.2); 52.0 it passes ("meep meep", turns
to A major); 54.8 a human stops it (skid, silence) | 56.0 calm F-major bridge | 64.0 theme A in D major,
"meep meep" at 68.8, zip out at 72.0 over the final chord, faded to silence at 73.6.
A noise riser lands on the downbeat of every scene change.

    uv run --with numpy --with scipy python video/music.py OUT.wav
"""

import itertools
import re
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48_000
DURATION = 73.6
BEAT = 0.4
BAR = 4 * BEAT
STEP = BEAT / 4  # one sixteenth
BARS = 46
SCENES = [0.0, 6.4, 12.8, 20.8, 30.4, 41.6, 56.0, 64.0]
FAIL, POOF, RESUME = 45.6, 46.4, 47.2
PASS, STOP = 52.0, 54.8
CTA_MEEP, ZIP = 68.8, 72.0
PEAK = 10 ** (-1 / 20)
N = round(SR * DURATION)
t_all = np.arange(N) / SR
rng = np.random.default_rng(1983)

LEAD_GAIN, HARMONY_GAIN, TRIANGLE_GAIN = 0.15, 0.11, 0.3
RELEASE = 0.02
VIBRATO_AFTER, VIBRATO_DEPTH = 0.15, 0.006


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def seconds(length):
    return np.arange(int(length * SR)) / SR


def stereo(mono, pan=0.0):
    # Equal-power pan, -1 left .. 1 right; `pan` may be a per-sample array.
    angle = (np.asarray(pan) + 1) * np.pi / 4
    return np.stack([mono * np.cos(angle), mono * np.sin(angle)], axis=1)


def place(buf, sig, at):
    start = round(at * SR)
    end = min(start + len(sig), len(buf))
    buf[start:end] += sig[: end - start]


def filt(sig, kind, freq, order=2):
    return sosfilt(butter(order, freq, btype=kind, fs=SR, output="sos"), sig, axis=0)


def envelope(t, attack, length, release):
    return np.clip(t / attack, 0, 1) * np.clip((length - t) / release, 0, 1)


def swept_band(sig, centers, width, block=240):
    # Bandpass whose centre follows `centers` (Hz per sample), recomputed every block with carried state.
    out = np.empty_like(sig)
    zi = np.zeros((2, 2))
    for i in range(0, len(sig), block):
        fc = min(centers[i], 14_000)
        sos = butter(2, [fc * (1 - width / 2), fc * (1 + width / 2)], btype="band", fs=SR, output="sos")
        out[i : i + block], zi = sosfilt(sos, sig[i : i + block], zi=zi)
    return out / np.sqrt(np.mean(out**2))


# ---- 2A03-ish oscillators ----


def poly_blep(phase, dt):
    out = np.zeros_like(phase)
    lo = phase < dt
    x = phase[lo] / dt[lo]
    out[lo] = 2 * x - x * x - 1
    hi = phase > 1 - dt
    x = (phase[hi] - 1) / dt[hi]
    out[hi] = x * x + 2 * x + 1
    return out


def pulse_wave(phase, dt, duty):
    # Band-limited pulse (PolyBLEP on both edges), DC removed.
    naive = np.where(phase < duty, 1.0, -1.0)
    return naive + poly_blep(phase, dt) - poly_blep((phase - duty) % 1, dt) - (2 * duty - 1)


def pulse_note(freq, dur, duty, gate, sustain, decay):
    held = dur * gate
    t = seconds(held + RELEASE)
    f = np.full_like(t, freq)
    if held > VIBRATO_AFTER + 0.1:
        f *= 1 + VIBRATO_DEPTH * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - VIBRATO_AFTER) / 0.1, 0, 1)
    phase = np.cumsum(f) / SR % 1
    env = (sustain + (1 - sustain) * np.exp(-t / decay)) * envelope(t, 0.002, held + RELEASE, RELEASE)
    return pulse_wave(phase, f / SR, duty) * env


def triangle_note(freq, dur, gate):
    # The 2A03 triangle walks a 32-step, 16-level staircase and has no volume control.
    held = dur * gate
    t = seconds(held + 0.004)
    step = np.floor((t * freq % 1) * 32)
    wave = np.where(step < 16, 15 - step, step - 16) / 7.5 - 1
    return wave * envelope(t, 0.002, held + 0.004, 0.004)


def noise_hold(n, rate):
    # White noise held at `rate` Hz, standing in for the noise channel's period register.
    hold = max(1, round(SR / rate))
    return np.repeat(rng.uniform(-1, 1, n // hold + 1), hold)[:n]


t = seconds(0.2)
KICK = np.sin(2 * np.pi * np.cumsum(48 + 110 * np.exp(-t * 40)) / SR) * np.exp(-t * 16)
KICK += noise_hold(len(t), 4000) * np.exp(-t * 80) * 0.35
t = seconds(0.22)
SNARE = noise_hold(len(t), 13_000) * np.exp(-t * 20) + 0.4 * np.sin(2 * np.pi * 185 * t) * np.exp(-t * 35)
t = seconds(0.06)
HAT = filt(noise_hold(len(t), SR), "high", 7000) * np.exp(-t * 80)
t = seconds(1.6)
CRASH = filt(noise_hold(len(t), 24_000), "high", 2500) * np.exp(-t * 2.6)

# duty, gate (fraction of the written length), sustain level, decay time
STYLES = {
    "bounce": (0.5, 0.7, 0.55, 0.1),
    "run": (0.125, 0.8, 0.6, 0.08),
    "stab": (0.25, 0.5, 0.35, 0.06),
    "sing": (0.25, 0.95, 0.8, 0.3),
    "calm": (0.25, 0.9, 0.45, 0.35),
    "soft": (0.125, 0.6, 0.3, 0.12),
}
TRIANGLE_GATES = {"stac": 0.6, "legato": 0.95}

# ---- score: note names with lengths in sixteenths (default 1), one string per bar ----

NOTE = re.compile(r"([A-G])([#b]?)(\d)")
PITCH_CLASS = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


def midi(name):
    letter, accidental, octave = NOTE.fullmatch(name).groups()
    return 12 * (int(octave) + 1) + PITCH_CLASS[letter] + {"#": 1, "b": -1, "": 0}[accidental]


def phrase(text):
    notes, pos = [], 0
    for token in text.split():
        name, _, length = token.partition(":")
        notes.append((pos, int(length or 1), None if name == "r" else midi(name)))
        pos += int(length or 1)
    assert pos == 16, text
    return notes


def at(bar, step):
    return bar * BAR + step * STEP


def play(voice, bar, bars, style, shift=0, vel=1.0):
    for i, text in enumerate(bars):
        for pos, length, m in phrase(text):
            if m is not None:
                voice.append((at(bar + i, pos), length * STEP, m + shift, vel, style))


JINGLE = ["C5:2 E5:2 G5:2 C6:4 G5:2 A5:2 B5:2", "C6:2 r:2 G5 G5 C6:2 E6:8"]
JINGLE_HARMONY = ["E4:2 G4:2 C5:2 E5:4 E5:2 F5:2 G5:2", "E5:2 r:2 E5 E5 E5:2 G5:8"]
JINGLE_BASS = ["C3:4 G2:4 C3:4 G2:4", "F2:4 G2:4 C3:8"]
PICKUP = "r:4 D5:2 r:2 B4:2 A4:2 G4 A4 F4:2"
THEME_A = [
    "G4:2 C5:2 E5:2 G5:3 E5 F5:2 E5:2 D5:2",
    "C5:2 D5:2 E5:4 A4:2 C5:2 D5:4",
    "E5:2 F5:2 G5:2 A5:3 G5 F5:2 E5:2 D5:2",
    "E5:2 C5:2 D5:2 B4:2 D5:6 r:2",
    "G4:2 C5:2 E5:2 G5:3 E5 F5:2 E5:2 D5:2",
    "C5:2 D5:2 E5:4 G5:2 A5:2 C6:4",
    "B5:2 A5:2 G5:2 E5:3 F5 G5:2 A5:2 B5:2",
    "C6:4 G5:2 E5:2 C5:4 r:4",
]
TURNAROUND = "E5 F5 F#5 G5 G#5 A5 A#5 B5 C6:2 B5:2 G#5:2 E5:2"
THEME_B = [
    "A4 C5 E5 A5 G#5 A5 E5:2 F5 E5 D#5 E5 C5:2 A4:2",
    "D5 F5 A5 D6 C#6 D6 A5:2 Bb5 A5 G#5 A5 F5:2 D5:2",
    "E5 G#5 B5 E6 D6 C6 B5 A5 G#5 F#5 E5 D5 C5 B4 A4 G#4",
    "A4:2 r:2 E5:2 r:2 A5:4 r:4",
]
B_TAG = "F5:2 r F5 r:2 G5:2 r G5 r:2 G#5:2 A5:2"
CLIMB = "E5 F5 F#5 G5 G#5 A5 A#5 B5 C6 C#6 D6 D#6 E6:4"
CHASE_RUN = "A5 G#5 A5 E5 C5 E5 A4 C5 E5 A5 C6 B5 A5 G#5 A5 E5"
CHASE_TURN = "F5 E5 F5 C5 A4 C5 F4 A4 B4 C5 D5 E5 F5 E5 D#5 E5"
CHASE = [
    CHASE_RUN,
    CHASE_TURN,
    "A5 B5 C6 D6 E6:2 F6:2 r:8",  # reaches for the top and fails at 45.6
    "r:8 E5 F5 F#5 G5 G#5 A5 B5 C6",  # pickup from 47.2
    CHASE_RUN,
    CHASE_TURN,
    "A5 C#6 E6 C#6 A5 E5 C#5 E5 r:8",  # passes: rest under the "meep meep"
    "D5 F#5 A5 F#5 D5 F#5 A5 D6 E5 G#5 B5 G#5 E5 G#5 B5 E6",
    "A5 C#6 E6 C#6 A5 C#6 E6 A6 r:8",  # cut by the skid at 54.8
]
BRIDGE = [
    "A5:6 G5:2 F5:4 C5:4",
    "D5:6 E5:2 F5:4 A5:4",
    "Bb5:6 A5:2 G5:4 D5:4",
    "E5:4 F5:4 G5:8",
    "A5:4 G5:2 E5:2 C#5:2 D5:2 E5:2 G5:2",
]
FINALE = [*THEME_A[:2], THEME_A[6], "C6:8 r:2 G5:2 A5:2 B5:2", "A5:2 G5:2 F5:2 A5:2 G5:2 B5:2 D6:2 B5:2"]

LEAD = [  # first bar, bars, style, transposition
    (0, JINGLE, "bounce", 0),
    (3, [PICKUP], "bounce", 0),
    (4, [*THEME_A, TURNAROUND], "bounce", 0),
    (13, [*THEME_B, THEME_B[0], B_TAG], "run", 0),
    (19, THEME_B, "bounce", -7),
    (23, [*THEME_B[:2], CLIMB], "run", 0),
    (26, CHASE, "run", 0),
    (35, BRIDGE, "calm", 0),
    (40, FINALE, "bounce", 2),
    (45, ["C6:16"], "sing", 2),
]

# One entry per bar; "X/Y" splits the bar in halves.
CHORDS = [
    "C",
    "C",
    "C",
    "G7",
    "C",
    "Am",
    "F",
    "G",
    "C",
    "Am",
    "G",
    "C",
    "E7",
    "Am",
    "Dm",
    "E7",
    "Am",
    "Am",
    "F/G",
    "Dm",
    "Gm",
    "A7",
    "Dm",
    "Am",
    "Dm",
    "E7",
    "Am",
    "F/E7",
    "Am",
    "E7",
    "Am",
    "F/E7",
    "A",
    "D/E",
    "A",
    "F",
    "Dm",
    "Bb",
    "C",
    "A7",
    "D",
    "Bm",
    "A",
    "D",
    "G/A",
    "D",
]
QUALITIES = {"": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10]}


def runs(*pairs):
    return [item for item, count in pairs for _ in range(count)]


BASS = runs(("jingle", 2), ("bounce", 11), ("drive", 22), ("walk", 5), ("bounce", 5), ("hold", 1))
PULSE2 = runs(
    (None, 2), ("arp8", 2), ("stab", 9), ("arp16", 10), (None, 12), ("arp8", 5), (None, 5), ("shimmer", 1)
)
DRUMS = runs(
    (None, 2), ("vamp", 1), ("vamp_fill", 1), ("bounce", 7), ("bounce_fill", 1), ("chase_fill", 1),
    ("chase", 5), ("chase_fill", 1), ("chase", 3), ("chase_fill", 1), ("chase", 2), ("roll", 1),
    ("chase", 3), ("pickup", 1), ("chase", 5), ("bridge", 4), ("bridge_fill", 1), ("bounce", 4),
    ("bounce_fill", 1), ("final", 1),
)  # fmt: skip
assert len(CHORDS) == len(BASS) == len(PULSE2) == len(DRUMS) == BARS

# kick / snare / hat; digits are velocity 1..9, one per sixteenth
DRUM_PATTERNS = {
    "vamp": ("9.......7.......", "", "..5...5...5...5."),
    "vamp_fill": ("9.......7.......", "..........4.5678", "..5...5........."),
    "bounce": ("9.....6.8.......", "....8.......8...", "6.4.6.4.6.4.6.4."),
    "bounce_fill": ("9.....6.8.......", "....8.......5679", "6.4.6.4.6.4....."),
    "chase": ("9...7...8...7...", "....8.......8...", "6262626262626262"),
    "chase_fill": ("9...7...8.......", "....8.....5.6789", "6262626262......"),
    "roll": ("9...7...8...9...", "1122334455667789", ""),
    "pickup": ("", "........34567899", ""),
    "bridge": ("6.......4.......", "............3...", "..3...3...3...3."),
    "bridge_fill": ("6.......4.......", "........23456789", "..3...3........."),
    "final": ("9...............", "", ""),
}
ARP8 = [0, 1, 2, 3, 2, 1, 0, 1]
DRIVE = [0, 12, 7, 12, 0, 12, 7, None]  # None: chromatic approach to the next bar's root
D_MAJOR = 2


def chord_at(bar, step):
    parts = CHORDS[bar].split("/")
    root, quality = re.fullmatch(r"([A-G][#b]?)(m|7|)", parts[step * len(parts) // 16]).groups()
    return midi(root + "0") % 12, QUALITIES[quality]


def voicing(chord, low):
    root, intervals = chord
    base = low + (root - low) % 12
    return [base + i for i in intervals] + [base + 12]


def bass_root(chord):
    return 36 + chord[0]


def third_below(m, key):
    scale = [0, 2, 4, 5, 7, 9, 11]
    degree = (m - key) % 12
    if degree not in scale:
        return m - 3
    return m - (degree - scale[(scale.index(degree) - 2) % 7]) % 12


# ---- voices ----

lead, harmony, bass = [], [], []  # (time, length, midi, velocity, style)
for bar, bars, style, shift in LEAD:
    play(lead, bar, bars, style, shift)


def lead_between(first, last):
    return [e for e in lead if at(first, 0) <= e[0] < at(last, 0)]


play(harmony, 0, JINGLE_HARMONY, "bounce", vel=0.7)
COPIES = [  # bars, pitch map, velocity, delay in sixteenths
    (23, 25, lambda m: m - 12, 0.6, 0),
    (25, 26, lambda m: m - 3, 0.55, 0),
    (26, 35, lambda m: m, 0.4, 3),  # chase echo, a dotted eighth behind
    (40, 45, lambda m: third_below(m, D_MAJOR), 0.6, 0),
]
for first, last, to, vel, delay in COPIES:
    harmony += [
        (time + delay * STEP, length, to(m), vel, style)
        for time, length, m, _, style in lead_between(first, last)
    ]

for bar, role in enumerate(PULSE2):
    if role == "arp8":
        for i in range(8):
            harmony.append(
                (at(bar, 2 * i), 2 * STEP, voicing(chord_at(bar, 2 * i), 60)[ARP8[i]], 0.55, "soft")
            )
    elif role == "arp16":
        for i in range(16):
            harmony.append((at(bar, i), STEP, voicing(chord_at(bar, i), 57)[i % 4], 0.4, "run"))
    elif role == "stab":
        for i, step in enumerate((2, 6, 10, 14)):
            harmony.append(
                (at(bar, step), 2 * STEP, voicing(chord_at(bar, step), 64)[1 + i % 2], 0.7, "stab")
            )
    elif role == "shimmer":
        tones = voicing(chord_at(bar, 0), 74)
        for i in range(32):
            harmony.append((at(bar, 0) + i * STEP / 2, STEP / 2, tones[i % 4], 0.7 * np.exp(-i / 12), "stab"))

play(bass, 0, JINGLE_BASS, "stac")
for bar, style in enumerate(BASS):
    root = bass_root(chord_at(bar, 0))
    if style == "bounce":
        for i in range(8):
            bass.append(
                (at(bar, 2 * i), 2 * STEP, bass_root(chord_at(bar, 2 * i)) + 12 * (i % 2), 1.0, "stac")
            )
    elif style == "drive":
        approach = bass_root(chord_at(bar + 1, 0)) - 1
        for i, interval in enumerate(DRIVE):
            note = approach if interval is None else bass_root(chord_at(bar, 2 * i)) + interval
            bass.append((at(bar, 2 * i), 2 * STEP, note, 1.0, "stac"))
    elif style == "walk":
        for i, interval in enumerate((0, 7, 12, 7)):
            bass.append((at(bar, 4 * i), 4 * STEP, root + interval, 0.6, "legato"))
    elif style == "hold":
        bass.append((at(bar, 0), BAR, root, 1.0, "legato"))


def render_pulse(events, gain):
    out = np.zeros(N)
    for time, length, m, vel, style in events:
        place(out, pulse_note(hz(m), length, *STYLES[style]) * vel * gain, time)
    return out


p1 = render_pulse(lead, LEAD_GAIN)
p2 = render_pulse(harmony, HARMONY_GAIN)
tri = np.zeros(N)
for time, length, m, vel, style in bass:
    place(tri, triangle_note(hz(m), length, TRIANGLE_GATES[style]) * vel * TRIANGLE_GAIN, time)
tri = filt(tri, "low", 6000)

drums, hats = np.zeros(N), np.zeros(N)
for bar, name in enumerate(DRUMS):
    if name is None:
        continue
    for (buf, sample, gain), row in zip(
        ((drums, KICK, 0.5), (drums, SNARE, 0.3), (hats, HAT, 0.12)), DRUM_PATTERNS[name], strict=False
    ):
        for step, level in enumerate(row):
            if level != ".":
                place(buf, sample * gain * int(level) / 9, at(bar, step))
for change in [*SCENES[1:], CTA_MEEP, ZIP]:
    place(drums, CRASH * 0.22, change)

# ---- gags ----


def riser(length):
    # Noise sweeping up, cut hard on the downbeat.
    t = seconds(length)
    u = t / length
    band = swept_band(rng.standard_normal(len(t)), 250 * 24**u, 0.8)
    return stereo(band * u**2.5 * np.clip((length - t) / 0.004, 0, 1), -0.5 + u)


def honk(root):
    # One "meep": a pulse dyad a major third wide, sagging slightly in pitch.
    t = seconds(0.12)
    bend = 1 - 0.07 * t / 0.12
    tone = sum(
        pulse_wave(np.cumsum(hz(m) * bend) / SR % 1, hz(m) * bend / SR, duty)
        for m, duty in ((root, 0.25), (root + 4, 0.5))
    )
    return filt(tone * envelope(t, 0.006, 0.12, 0.02), "low", 7000)


def meep():
    out = np.zeros(int(0.34 * SR))
    for start in (0.0, 0.22):
        place(out, honk(81), start)
    return out


def slide_whistle(length):
    t = seconds(length)
    f = 1900 * (380 / 1900) ** ((t / length) ** 1.6) * (1 + 0.006 * np.sin(2 * np.pi * 6 * t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    breath = filt(rng.standard_normal(len(t)), "band", [1500, 5000]) * 0.04
    return (np.sin(phase) + 0.12 * np.sin(2 * phase) + breath) * envelope(t, 0.03, length, 0.08)


def poof():
    t = seconds(0.6)
    puff = filt(rng.standard_normal(len(t)), "low", 600) * (1 - np.exp(-t * 120)) * np.exp(-t * 7) * 0.6
    thud = np.sin(2 * np.pi * np.cumsum(40 + 40 * np.exp(-t * 10)) / SR) * np.exp(-t * 14)
    return puff + thud * 0.8


def skid(length):
    t = seconds(length)
    u = t / length
    band = swept_band(rng.standard_normal(len(t)), 3200 * (500 / 3200) ** u, 0.35)
    squeal = np.sin(2 * np.pi * np.cumsum(1500 - 800 * u) / SR) * 0.25
    return (band * (1 + 0.35 * np.sin(2 * np.pi * 38 * t)) * 0.3 + squeal) * envelope(t, 0.01, length, 0.12)


def zip_whoosh(length):
    t = seconds(length)
    u = t / length
    band = swept_band(rng.standard_normal(len(t)), 600 * 16 ** (u**0.7), 0.6)
    chirp = np.sin(2 * np.pi * np.cumsum(500 + 3000 * u**0.7) / SR) * 0.3
    return stereo((band * 0.25 + chirp) * np.sin(np.pi * u) ** 2, -0.7 + 1.4 * u)


fx, fx_send = np.zeros((N, 2)), np.zeros((N, 2))


def cue(sig, time, wet):
    place(fx, sig, time)
    place(fx_send, sig * wet, time)


for change in SCENES[1:]:
    length = {SCENES[6]: 0.08, SCENES[7]: 1.2}.get(change, 0.6)
    cue(riser(length) * (0.16 if change == SCENES[7] else 0.1), change - length, 0.3)
for time in (PASS, CTA_MEEP):
    cue(stereo(meep() * 0.3, 0.1), time, 0.4)
whistle = stereo(slide_whistle(POOF - FAIL) * 0.24, -0.2)
WHISTLE_WET = 0.5
cue(whistle, FAIL, WHISTLE_WET)
cue(stereo(poof() * 0.22), POOF, 1.5)
cue(stereo(skid(0.45) * 0.4), STOP, 0.0)  # dry, so the stop is followed by true silence
cue(zip_whoosh(0.3) * 0.5, ZIP, 0.4)
whistle_track = np.zeros((N, 2))
place(whistle_track, whistle, FAIL)

# ---- mix ----


def room(length, decay):
    t = seconds(length)
    ir = rng.standard_normal((len(t), 2)) * np.exp(-t * decay)[:, None]
    ir = filt(ir, "low", 5000)
    return ir / np.sqrt((ir**2).sum(axis=0))


def reverb(send, ir):
    return np.stack([fftconvolve(send[:, c], ir[:, c])[:N] for c in range(2)], axis=1)


# Music gate: hard cuts for the failed run and the human stop, ducks under each "meep meep".
gate = np.interp(
    t_all,
    [0, FAIL - 0.006, FAIL, RESUME - 0.002, RESUME, PASS - 0.03, PASS, PASS + 0.4, PASS + 0.55,
     STOP - 0.01, STOP + 0.02, SCENES[6] - 0.002, SCENES[6], CTA_MEEP + 0.02, CTA_MEEP + 0.06,
     CTA_MEEP + 0.4, CTA_MEEP + 0.6, DURATION],
    [1, 1, 0, 0, 1, 1, 0.4, 0.4, 1, 1, 0, 0, 1, 1, 0.55, 0.55, 1, 1],
)[:, None]  # fmt: skip

dry = stereo(p1, -0.3) + stereo(p2, 0.3) + stereo(tri) + stereo(drums) + stereo(hats, 0.15)
send = stereo(p1, -0.3) * 0.5 + stereo(p2, 0.3) * 0.6 + stereo(drums) * 0.2 + stereo(hats, 0.15) * 0.3
music = (dry + 0.25 * reverb(send * gate, room(1.2, 6))) * gate
GAG_ROOM, GAG_WET = room(0.6, 9), 0.3
gags = fx + GAG_WET * reverb(fx_send, GAG_ROOM)
whistle_track += GAG_WET * reverb(whistle_track * WHISTLE_WET, GAG_ROOM)  # the whistle stem, for the report
fade = (np.interp(t_all, [0, 0.003, ZIP + 0.4, DURATION], [0, 1, 1, 0]) ** 2)[:, None]
total = (music + gags) * fade

highpassed = filt(total, "high", 30)
drive = 1.25 / np.abs(highpassed).max()
makeup = PEAK / np.abs(np.tanh(highpassed * drive)).max()


def master(x):
    return np.tanh(filt(x, "high", 30) * drive) * makeup


out = np.round(master(total) * 32767).astype(np.int16)
wavfile.write(sys.argv[1], SR, out)

# ---- report ----


def rms_db(x, start, end):
    seg = x[round(start * SR) : round(end * SR)].astype(float) / 32767
    return 10 * np.log10(np.mean(seg**2) + 1e-12)


def onset_near(x, target, search=0.06, window=0.01, floor_db=-50):
    # The time where energy in the next 10 ms most exceeds the previous 10 ms; the floor keeps a
    # crescendo out of silence from counting as an attack.
    energy = np.concatenate([[0.0], np.cumsum((x.astype(float).mean(axis=1) / 32767) ** 2)])
    w = round(window * SR)
    floor = 10 ** (floor_db / 10) * w
    times = target + np.arange(-search, search, 0.001)
    idx = np.round(times * SR).astype(int)
    ratio = (energy[idx + w] - energy[idx] + floor) / (energy[idx] - energy[idx - w] + floor)
    return times[np.argmax(ratio)]


without_whistle = np.round(master(total - whistle_track * fade) * 32767)
print(f"wrote {sys.argv[1]}: {len(out) / SR:.3f} s, {SR} Hz, {out.shape[1]} ch, 16-bit")
peak_db = 20 * np.log10(np.abs(out.astype(float)).max() / 32767)
print(f"peak {peak_db:.2f} dBFS, full-scale samples {(np.abs(out.astype(int)) >= 32767).sum()}")
bounds = [*SCENES, DURATION]
scene_rms = [f"{a:g}-{b:g} {rms_db(out, a, b):.1f}" for a, b in itertools.pairwise(bounds)]
print("scene RMS dBFS: " + ", ".join(scene_rms))
for label, x, window, around in (
    ("fail gap (no whistle)", without_whistle, (45.65, 46.35), [(44.0, 45.6), (48.0, 49.6)]),
    ("stop gap", out, (55.3, 55.9), [(53.2, 54.8), (56.0, 57.6)]),
):
    gap = rms_db(x, *window)
    surround = np.mean([rms_db(out, *span) for span in around])
    print(f"{label} {window}: {gap:.1f} dBFS vs music {surround:.1f} dBFS -> {surround - gap:.1f} dB below")
print(f"fail gap with whistle: {rms_db(out, 45.65, 46.35):.1f} dBFS")
targets = [*SCENES[1:], PASS, CTA_MEEP]
print("onsets (ms off): " + ", ".join(f"{x:g} {1000 * (onset_near(out, x) - x):+.0f}" for x in targets))
