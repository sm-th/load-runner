"""A stand-in for the `buzz` CLI that keeps the documented contract
(github.com/block/buzz, crates/buzz-cli/README.md and messages.rs), backed by a JSON file.

- Writes print `{event_id, accepted, message}`; reads print arrays of Nostr events
  `{id, pubkey, kind, content, created_at, tags, sig}` sorted oldest first.
- `messages get` returns the newest `--limit` events matching `#h`, `kinds`, `since` (inclusive).
- Replies carry NIP-10 `e` tags marked `root` and `reply`.
- Errors print `{"error", "message"}` on stderr and exit 1.
- The identity is BUZZ_PRIVATE_KEY; its display name is the key itself.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

STATE = Path(os.environ["FAKE_BUZZ_STATE"])
CHANNEL = os.environ["FAKE_BUZZ_CHANNEL"]


def fail(message: str) -> None:
    print(json.dumps({"error": "not_found", "message": message}), file=sys.stderr)
    sys.exit(1)


def pubkey(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("group")
    parser.add_argument("command")
    parser.add_argument("--channel")
    parser.add_argument("--content")
    parser.add_argument("--reply-to")
    parser.add_argument("--event")
    parser.add_argument("--since", type=int)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--kinds")
    parser.add_argument("--pubkey", action="append")
    args = parser.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {"events": [], "profiles": {}}
    key = os.environ["BUZZ_PRIVATE_KEY"]
    me = pubkey(key)
    state["profiles"][me] = {"pubkey": me, "display_name": key}

    if args.channel is not None and args.channel != CHANNEL:
        fail("channel not found")
    events = state["events"]
    by_id = {e["id"]: e for e in events}
    match (args.group, args.command):
        case ("messages", "send"):
            content = sys.stdin.read() if args.content == "-" else args.content
            tags = [["h", CHANNEL]]
            if args.reply_to:
                parent = by_id.get(args.reply_to) or fail("parent event not found")
                marked = {t[3]: t[1] for t in parent["tags"] if t[0] == "e"}
                tags += [
                    ["e", marked.get("root", parent["id"]), "", "root"],
                    ["e", parent["id"], "", "reply"],
                ]
            event_id = hashlib.sha256(f"{len(events)}{content}".encode()).hexdigest()
            events.append(
                {
                    "id": event_id,
                    "pubkey": me,
                    "kind": 9,
                    "content": content,
                    "created_at": int(time.time()),
                    "tags": tags,
                    "sig": "0" * 128,
                }
            )
            print(json.dumps({"event_id": event_id, "accepted": True, "message": ""}))
        case ("messages", "get"):
            found = [e for e in events if args.since is None or e["created_at"] >= args.since]
            print(json.dumps(found[-args.limit :]))
        case ("messages", "thread"):
            root = by_id.get(args.event) or fail("event not found")
            replies = [e for e in events if any(t[0] == "e" and t[1] == root["id"] for t in e["tags"])]
            print(json.dumps([root, *replies][: args.limit]))
        case ("users", "get"):
            keys = args.pubkey or [me]
            print(json.dumps([state["profiles"][k] for k in keys if k in state["profiles"]]))
        case _:
            fail(f"unknown command {args.group} {args.command}")
    STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
