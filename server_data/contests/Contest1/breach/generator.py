import random
import sys

a = random.randint(-100, 100)
b = random.randint(-100, 100)

print(f"{a} {b}")
print(a + b, file=sys.stderr)

# The generator should print the INPUT to standard output
# and the corresponding EXPECTED OUTPUT to standard error.
