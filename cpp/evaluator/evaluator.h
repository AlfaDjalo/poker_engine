#pragma once

#include <vector>
#include <cstdint>

enum class ScoreType {
    HIGH = 0,
    LOW_27 = 1,
    LOW_UNQUAL = 2,
    LOW_QUAL = 3,
    BADUGI = 4
};

std::vector<std::vector<int>> evaluate_hands(
    const std::vector<uint64_t>& player_masks,
    uint64_t board_mask,
    ScoreType score_type
);

