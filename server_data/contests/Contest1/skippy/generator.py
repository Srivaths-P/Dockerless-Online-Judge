from random import choice, randint
from string import ascii_lowercase
import sys

n = randint(0, 100)
s = ''.join(choice(ascii_lowercase) for _ in range(n))

print(s)
print(s[::-1], file=sys.stderr)

# The generator should print the INPUT to standard output
# and the corresponding EXPECTED OUTPUT to standard error.