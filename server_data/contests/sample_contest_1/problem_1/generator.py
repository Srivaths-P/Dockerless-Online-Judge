import string
import sys
import random

N = random.randint(1, 10)
S = ''.join(random.choice(string.ascii_lowercase + string.ascii_uppercase) for _ in range(N))

print(S, file=sys.stdout)
print(f"Hello, {S}!", file=sys.stderr)