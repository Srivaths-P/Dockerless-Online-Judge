from random import choice, randint
from string import ascii_letters
import sys

is_pal = randint(0, 1)

n = randint(1, 15)
if not is_pal:
    cnts = [0] * 26
    for _ in range(n):
        cnts[randint(0, 25)] += 1

    print(' '.join(chr(i + ord('a')) * cnt for i, cnt in enumerate(cnts) if cnt > 0), file=sys.stderr)

else:
    half = ''.join(choice(ascii_letters) for _ in range(n // 2))
    mid = choice(ascii_letters) if n % 2 else ''
    s = half + mid + half[::-1]

print(s)
print(f"{'YES' if s == s[::-1] else 'NO'}", file=sys.stderr)
