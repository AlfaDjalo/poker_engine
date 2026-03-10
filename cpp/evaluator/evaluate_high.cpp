#include <vector>
#include <cstdint>
#include <algorithm>

using std::vector;

static void mask_to_ranks(uint64_t mask, vector<int>& ranks)
{
    for (int c = 0; c < 52; c++)
    {
        if (mask & (1ULL << c))
        {
            int rank = c / 4;
            ranks.push_back(rank);
        }
    }
}

static vector<int> score_high_card(vector<int> ranks)
{
    std::sort(ranks.begin(), ranks.end(), std::greater<int>());
    ranks.resize(5);

    vector<int> score;
    score.push_back(0);
    score.insert(score.end(), ranks.begin(), ranks.end());

    return score;
}

vector<vector<int>> evaluate_high(
    const vector<uint64_t>& player_masks,
    uint64_t board_mask
)
{
    vector<vector<int>> results;

    for (uint64_t player_mask : player_masks)
    {
        uint64_t combined = player_mask | board_mask;

        vector<int> ranks;
        mask_to_ranks(combined, ranks);

        results.push_back(score_high_card(ranks));
    }

    return results;
}