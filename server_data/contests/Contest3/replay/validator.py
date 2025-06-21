#!/usr/bin/env python3
import sys
from collections import Counter

# This validator receives file paths as command-line arguments from the judge engine.
# sys.argv[1]: Path to the problem's input file.
# sys.argv[2]: Path to the user's generated output file.
# sys.argv[3]: Path to the problem's official/expected output file. (Not used in this validator)

def judge_error(message: str):
    """
    Exits with code 2 for judge errors (e.g., malformed input, validator crash).
    This signals an "Internal Error" verdict.
    """
    print(f"Judge Error: {message}", file=sys.stderr)
    sys.exit(2)


def wrong_answer(message: str):
    """
    Exits with code 1 for a "Wrong Answer" verdict.
    """
    # print(f"WA: {message}", file=sys.stderr)
    sys.exit(1)


def accept():
    """
    Exits with code 0 for an "Accepted" verdict.
    """
    sys.exit(0)


def main():
    if len(sys.argv) < 4:
        judge_error(f"Validator was called with insufficient arguments. Got {len(sys.argv) - 1}, expected 3.")

    problem_input_path = sys.argv[1]
    user_output_path = sys.argv[2]
    # expected_output_path = sys.argv[3]

    try:
        with open(problem_input_path, 'r') as f:
            # The input format is a line of space-separated integers
            expected_freq_list = list(map(int, f.read().strip().split()))
        if len(expected_freq_list) != 26:
            judge_error(f"Problem input file has {len(expected_freq_list)} numbers, expected 26.")
    except (IOError, ValueError) as e:
        judge_error(f"Could not read or parse the problem's input file: {e}")

    # --- 3. Read User's Output ---
    user_output_str = ""

    try:
        with open(user_output_path, 'r') as f:
            user_output_str = f.read().strip()
    except IOError:
        # If the user's program produces no output file, treat it as an empty string.
        pass

    odd_freq_count = 0
    for freq in expected_freq_list:
        if freq < 0:
            judge_error("Problem input contains negative frequency.")
        if freq % 2 != 0:
            odd_freq_count += 1

    # Validation
    is_possible = (odd_freq_count <= 1)

    if not is_possible:
        if user_output_str == "-1":
            accept()
        else:
            wrong_answer(f"A palindrome is impossible, but user printed '{user_output_str}' instead of '-1'.")
    else:
        if user_output_str == "-1":
            wrong_answer("A palindrome is possible, but user printed '-1'.")

        if user_output_str != user_output_str[::-1]:
            wrong_answer("The output string is not a palindrome.")

        user_freq_map = Counter(user_output_str)

        user_freq_list = [0] * 26
        for char, count in user_freq_map.items():
            if 'a' <= char <= 'z':
                user_freq_list[ord(char) - ord('a')] = count
            else:
                wrong_answer(f"Output contains an invalid character: '{char}'.")

        if user_freq_list != expected_freq_list:
            wrong_answer("The letters or their frequencies in the output do not match the problem input.")

        accept()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Catch any unexpected crashes in the validator itself.
        judge_error(f"An uncaught exception occurred in the validator: {e}")