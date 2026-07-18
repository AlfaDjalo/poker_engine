#pragma once

#include <vector>
#include <cstdint>

std::vector<std::vector<int>> evaluate_low_27(
    const std::vector<uint64_t>& player_masks,
    uint64_t board_mask
);