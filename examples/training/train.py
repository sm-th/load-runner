"""A toy training loop: gradient descent on y = 2x. Too high a learning rate diverges."""

import argparse
import math
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--lr", type=float, required=True)
parser.add_argument("--epochs", type=int, default=5)
args = parser.parse_args()

xs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
w = 1.5
loss = math.nan
for epoch in range(1, args.epochs + 1):
    for _ in range(2):
        errors = [(w - 2) * x for x in xs]
        w -= args.lr * 2 * sum(e * x for e, x in zip(errors, xs, strict=True)) / len(xs)
    loss = sum(((w - 2) * x) ** 2 for x in xs) / len(xs)
    if not math.isfinite(loss) or loss > 1e6:  # a float32 trainer would hit nan a few steps later
        print(f"epoch {epoch} loss nan")
        print("diverged: lower the learning rate", file=sys.stderr)
        sys.exit(1)
    print(f"epoch {epoch} loss {loss:.3g}")
    time.sleep(0.4)

print(f"::result loss={loss:.3g} w={w:.4f}")
