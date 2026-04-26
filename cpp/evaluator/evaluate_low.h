#pragma once

#include <cstdint>

namespace poker_eval {

uint64_t evaluate_low_a5(uint64_t hole_mask, uint64_t board_mask, int showdown_type, uint64_t& best_mask_out);
uint64_t evaluate_low_27(uint64_t hole_mask, uint64_t board_mask, int showdown_type, uint64_t& best_mask_out);

}  // namespace poker_eval
