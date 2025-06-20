from random import randint, shuffle
from string import ascii_lowercase
import sys

is_pal = randint(0, 1)

n = randint(1, 10 ** 2)
if not is_pal:
    cnts = [0] * 26
    for _ in range(n):
        cnts[randint(0, 25)] += 1

else:
    cnts = [0] * 26
    for _ in range(n // 2):
        cnts[randint(0, 25)] += 2

    if n % 2 == 1:
        cnts[randint(0, 25)] += 1

print(*cnts)

ans = ''
mid = ''
for i in range(26):
    if cnts[i] % 2 == 1:
        if mid:
            print(-1, file=sys.stderr)
            break

        mid = ascii_lowercase[i]

    ans += ascii_lowercase[i] * (cnts[i] // 2)

else:
    ans = list(ans)
    shuffle(ans)
    ans = ans + [mid] + ans[::-1]
    print(''.join(ans), file=sys.stderr)
