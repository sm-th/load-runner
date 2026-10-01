"""A scripted stand-in for an LLM brain, so the example runs offline and costs nothing.

It reads the prompt (protocol brief + thread transcript) on stdin and answers like
an agent would. Replace it with `claude -p`, `codex exec`, or your harness.
"""

import re
import sys

transcript = sys.stdin.read().split("\nThread:\n", 1)[-1]
messages = re.split(r"\n(?=\[\d\d:\d\d:\d\d\] )", transcript.strip())
last = messages[-1]
author, _, text = last.partition("] ")[2].partition(": ")
params = re.findall(r"^lr = (\S+)$", transcript, re.M)
lr = float(params[-1]) if params else 0.1

if text.startswith("✗") and "nan" in transcript.rsplit("▶", 1)[-1]:
    print(f"Loss diverged to nan at lr = {lr:g}. Lowering the learning rate.")
    print(f"/set lr={lr / 10:g}")
    print("/restart")
elif text.startswith("✗"):
    print("The run failed without diverging; a person should look at the output.")
elif text.startswith("✓"):
    print("Got it, everything is okay.")
elif text[:1] not in "▶▹■↻⚙⊘":
    print(f"Noted, {author}.")
