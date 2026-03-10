#pragma once
#include <vector>

inline void choose_recursive(
    int start,
    int n,
    int k,
    std::vector<int>& current,
    std::vector<std::vector<int>>& result
)
{
    if (current.size() == (size_t)k)
    {
        result.push_back(current);
        return;
    }

    for (int i = start; i < n; i++)
    {
        current.push_back(i);
        choose_recursive(i + 1, n, k, current, result);
        current.pop_back();
    }
}

inline std::vector<std::vector<int>> choose(int n, int k)
{
    std::vector<std::vector<int>> result;
    std::vector<int> current;

    choose_recursive(0, n, k, current, result);

    return result;
}