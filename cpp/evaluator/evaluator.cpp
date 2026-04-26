#include "score_types.hpp"
#include "evaluate_low.h"

#include <vector>
#include <cstdint>
#include <utility>
#include <tuple>
#include <iostream>  // Added for debug prints

std::pair<int, uint64_t> evaluate_holdem_high(uint64_t, uint64_t);
std::pair<int, uint64_t>  evaluate_omaha_high(uint64_t, uint64_t);
std::pair<int, uint64_t>  evaluate_make5_high(uint64_t, uint64_t);
std::pair<int, uint64_t>  evaluate_draw_high(uint64_t);

std::vector<std::vector<int64_t>> evaluate_hands(
    const std::vector<uint64_t>& hole_masks,
    uint64_t board_mask,
    ScoreType score_type,
    ShowdownType showdown_type
)
{
    std::vector<std::vector<int64_t>> results;

    // std::cout << "DEBUG: score_type=" << score_type << std::endl;
    // std::cout << "DEBUG: showdown_type=" << showdown_type << std::endl;

    for (auto hole:hole_masks)
    {
        // ------------------------
        // HIGH HAND
        // ------------------------
        
        if (score_type == ScoreType::HIGH)
        {
            std::cout << "DEBUG: score_type=HIGH" << std::endl;
            int score = 0;
            uint64_t best_mask = 0;

            switch(showdown_type)
            {
                case ShowdownType::HOLDEM:
                    std::tie(score, best_mask) = evaluate_holdem_high(hole, board_mask);
                    break;

                case ShowdownType::OMAHA:
                    std::tie(score, best_mask) = evaluate_omaha_high(hole, board_mask);
                    break;

                case ShowdownType::MAKE5:
                    std::tie(score, best_mask) = evaluate_make5_high(hole, board_mask);
                    break;

                case ShowdownType::DRAW:
                    std::tie(score, best_mask) = evaluate_draw_high(hole);
                    break;

                default:
                    score = 0; best_mask = 0;
            }

            results.push_back({(int64_t)score, (int64_t)best_mask});
            continue;
        }

        // ------------------------
        // LOW A5
        // ------------------------
        if (score_type == ScoreType::LOW_A5)
        {
            std::cout << "DEBUG: Entering LOW_A5 evaluation for hole=" << hole << " board=" << board_mask << std::endl;
            uint64_t best_mask = 0;
            uint64_t score =
                poker_eval::evaluate_low_a5(hole, board_mask, (int)showdown_type, best_mask);
            std::cout << "DEBUG: LOW_A5 score=" << score << std::endl;

            results.push_back({ (int64_t)score, (int64_t)best_mask });
            continue;
        }    
    
        // ------------------------
        // LOW 27
        // ------------------------
        if (score_type == ScoreType::LOW_27)
        {
            std::cout << "DEBUG: score_type=LOW_27" << std::endl;
            uint64_t best_mask = 0;
            uint64_t score =
                poker_eval::evaluate_low_27(hole, board_mask, (int)showdown_type, best_mask);

            results.push_back({ (int64_t)score, (int64_t)best_mask });
            continue;
        }

        // ------------------------
        // FALLBACK
        // ------------------------
        results.push_back({0, 0});
    }
    
    return results;
}