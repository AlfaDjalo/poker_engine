#pragma once
#include <cstdint>
#include <array>
#include <algorithm>

inline int rank_of(int card)
{
    return card % 13;
}

inline int suit_of(int card)
{
    return card / 13;
}

inline int rank_high_5(uint64_t mask)
{
    std::array<int, 5> cards_arr;
    int idx = 0;

    for (int i = 0; i < 52 && idx < 5; i++)
        if (mask & (1ULL << i))
            cards_arr[idx++] = i;

    std::array<int, 5> ranks, suits;
    for (int i = 0; i < 5; i++) {
        ranks[i] = cards_arr[i] % 13;
        suits[i] = cards_arr[i] / 13;
    }
    std::sort(ranks.begin(), ranks.end());

    bool flush = true;
    for (int i = 1; i < 5; i++)
        if (suits[i] != suits[0]) { flush = false; break; }

    bool straight = (ranks[4]-ranks[0] == 4 &&
                    ranks[1] == ranks[0] + 1 &&
                    ranks[2] == ranks[0] + 2 &&
                    ranks[3] == ranks[0] + 3);

    if (!straight && ranks[0] == 0 && ranks[1] == 1 &&
        ranks[2] == 2 && ranks[3] == 3 && ranks[4] == 12) {
            straight = true;
            ranks = {0, 1, 2, 3, 4};
    }

    std::array<int, 13> freq{};
    for (int r : ranks) freq[r]++;

    std::array<int, 5> sorted_by_freq = ranks;
    std::sort(sorted_by_freq.begin(), sorted_by_freq.end(),
        [&](int a, int b) {
            return freq[a] != freq[b] ? freq[a] > freq[b] : a > b;
        });

    int score = 0;

    for (int r: sorted_by_freq)
        score = score * 13 + r;

    int maxf = *std::max_element(freq.begin(), freq.end());
    int pairs = 0;
    for (int f : freq) if (f == 2) pairs++;

    if (straight && flush)              return 8000000 + score;
    else if (maxf == 4)                 return 7000000 + score;
    else if (maxf == 3 && pairs == 1)   return 6000000 + score;
    else if (flush)                     return 5000000 + score;
    else if (straight)                  return 4000000 + score;
    else if (maxf == 3)                 return 3000000 + score;
    else if (pairs == 2)                return 2000000 + score;
    else if (pairs == 1)                return 1000000 + score;
    else                                return score;
}