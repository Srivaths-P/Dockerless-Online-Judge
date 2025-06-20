## Task

Zero wants to create a command that creates a palindrome to make sure he's not losing track of time. Unfortunately, he has only a limited number of letters available.

He has to use all the letters he has, or the psychiatrist will find out that he is not taking his medication.

Tell Zero how to create a palindrome using the letters he has, or tell him that it is impossible.

### Input Format

The first line contains an array of integers $A$, where each integer represents the frequency of the corresponding letter in the alphabet.

### Output Format

Print any palindrome that can be created using the given frequency of letters. If it is not possible to create a palindrome, print `-1`.

### Constraints

*  $|A| = 26$
*   $1 \leq \sum A_i \leq 10^5$.

### Sample Input
```
4 0 0 0 0 2 0 0 0 1 0 0 0 2 2 0 0 2 0 2 2 0 0 0 0 0
```

### Sample Output
```
anutforajaroftuna
```