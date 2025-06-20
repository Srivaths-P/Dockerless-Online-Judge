import sys


# sys.argv[1]: path to the input file
# sys.argv[2]: path to the user's output file
# sys.argv[3]: path to the expected output file


def get_user_output() -> str:
    """
    Return the user's output in the same format as the expected output.
    You can read from sys.stdin or from a file if the user's output is stored in a file.
    """
    return open(sys.argv[2]).read().strip()


def get_expected_output():
    """
    Return the expected output for the problem. DO NOT print the expected output directly.
    You can open sys.argv[3] if the expected output is stored in a file.
    """
    return open(sys.argv[3]).read().strip()


def is_valid_output(expected_output, user_output) -> bool:
    """
    Check if the user's output matches the expected output.
    Return True if the user's output is valid, False otherwise.
    """
    print(f"Expected output: {expected_output}", file=sys.stderr)
    print(f"User output: {user_output}", file=sys.stderr)
    return user_output.lower() == expected_output.lower()


def _main():
    """
    Avoid changing this function unless you know what you are doing.

    This function reads the input file and the user's output file, compares the
    user's output with the expected output, and exits with the appropriate status code.
    """
    try:
        # Redirect stdin to read from the input file.
        with open(sys.argv[1]) as f:
            sys.stdin = f

        user_output = get_user_output()
        expected_output = get_expected_output()

    except (IOError, ValueError):
        sys.exit(1)

    if is_valid_output(expected_output, user_output):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    _main()
