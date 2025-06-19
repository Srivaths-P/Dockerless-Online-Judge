from random import choice, randint
from string import ascii_letters
import sys

is_pal = randint(0, 1)

n = randint(1, 15)
if not is_pal:
    s = ''.join(choice(ascii_letters) for _ in range(n))
    while s == s[::-1]:
        s = ''.join(choice(ascii_letters) for _ in range(n))

else:
    half = ''.join(choice(ascii_letters) for _ in range(n // 2))
    mid = choice(ascii_letters) if n % 2 else ''
    s = half + mid + half[::-1]

print(s)
print(f"{'YES' if s == s[::-1] else 'NO'}", file=sys.stderr)
