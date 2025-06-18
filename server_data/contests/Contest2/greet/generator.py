from random import choice, randint
from string import ascii_letters
import sys

n = randint(0, 100)
s = ''.join(choice(ascii_letters) for _ in range(n))

print(s)
print(f'Hello, {s}', file=sys.stderr)

# The generator should print the INPUT to standard output
# and the corresponding EXPECTED OUTPUT to standard error.
