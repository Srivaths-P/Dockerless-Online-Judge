#include <bits/stdc++.h>
using namespace std;

int main() {
    srand(time(0));

    bool is_pal = rand() % 2;
    int n = rand() % 20 + 1;
    vector<int> cnts(26, 0);

    if (!is_pal) {
        for (int i = 0; i < n; ++i) {
            cnts[rand() % 26]++;
        }
    } else {
        for (int i = 0; i < n / 2; ++i) {
            cnts[rand() % 26] += 2;
        }
        if (n % 2 == 1) {
            cnts[rand() % 26]++;
        }
    }

    for (int i = 0; i < 26; ++i)
        cout << cnts[i] << ' ';
    cout << endl;

    string ans = "", mid = "";
    for (int i = 0; i < 26; ++i) {
        if (cnts[i] % 2 == 1) {
            if (!mid.empty()) {
                cerr << -1 << endl;
                return 0;
            }
            mid = string(1, 'a' + i);
        }
        ans += string(cnts[i] / 2, 'a' + i);
    }

    random_device rd;
    mt19937 g(rd());
    shuffle(ans.begin(), ans.end(), g);

    string final_str = ans + mid + string(ans.rbegin(), ans.rend());
    cerr << final_str << endl;

    return 0;
}
