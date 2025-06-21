#include <iostream>
#include <fstream>
#include <string>
#include <algorithm>
#include <cctype>

// This validator receives file paths as command-line arguments from the judge engine.
// argv[1]: Path to the problem's input file. (Not used in this validator)
// argv[2]: Path to the user's generated output file.
// argv[3]: Path to the problem's official/expected output file.

// Exit with code 2 for judge errors (e.g., file read errors).
// This signals an "Internal Error" verdict.
void judge_error(const std::string& msg) {
    std::cerr << "Judge Error: " << msg << std::endl;
    exit(2);
}

// Exit with code 1 for a "Wrong Answer" verdict.
void wrong_answer() {
    exit(1);
}

// Exit with code 0 for an "Accepted" verdict.
void accept() {
    exit(0);
}

// Helper function to convert a string to lowercase.
std::string to_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c){ return std::tolower(c); });
    return s;
}

std::string trim(const std::string& s) {
    const std::string whitespace = " \t\n\r\f\v";
    size_t first = s.find_first_not_of(whitespace);
    if (std::string::npos == first) {
        return "";
    }
    size_t last = s.find_last_not_of(whitespace);
    return s.substr(first, (last - first + 1));
}


int main(int argc, char* argv[]) {
    if (argc < 4) {
        judge_error("Validator was called with insufficient arguments.");
    }

//    std::string problem_input_path = argv[1];
    std::string user_output_path = argv[2];
    std::string expected_output_path = argv[3];

    std::ifstream user_output_file(user_output_path);
    std::string user_output_str = "";
    if (user_output_file.is_open()) {
        user_output_str.assign(
            (std::istreambuf_iterator<char>(user_output_file)),
            (std::istreambuf_iterator<char>())
        );
        user_output_file.close();
    } else {
        // If the user's program produces no output file, treat it as an empty string.
    }

    std::ifstream expected_output_file(expected_output_path);
    std::string expected_output_str;
    if (expected_output_file.is_open()) {
        expected_output_str.assign(
            (std::istreambuf_iterator<char>(expected_output_file)),
            (std::istreambuf_iterator<char>())
        );
        expected_output_file.close();
    } else {
        judge_error("Could not open the official expected output file.");
    }

    // Validation
    std::string user_trimmed = trim(user_output_str);
    std::string expected_trimmed = trim(expected_output_str);

    if (to_lower(user_trimmed) == to_lower(expected_trimmed)) {
        accept();
    } else {
        wrong_answer();
    }

    return 0;
}