#include "score_types.hpp"

#include <vector>
#include <cstdint>


// #include "evaluator.h"

// #include <stdexcept>

// #include "evaluate_high.h"
// #include "evaluate_low_27_eval.h"
// #include "evaluate_low_unqual.h"
// #include "evaluate_low_qual.h"
// #include "evaluate_badugi.h"

int evaluate_holdem_high(uint64_t, uint64_t);
int evaluate_omaha_high(uint64_t, uint64_t);
int evaluate_make5_high(uint64_t, uint64_t);
int evaluate_draw_high(uint64_t);

std::vector<std::vector<int>> evaluate_hands(
    const std::vector<uint64_t>& hole_masks,
    uint64_t board_mask,
    ScoreType score_type,
    ShowdownType showdown_type
)
{
    std::vector<std::vector<int>> results;

    for (auto hole:hole_masks)
    {
        int score = 0;

        if (score_type == ScoreType::HIGH)
        {
            switch(showdown_type)
            {
                case ShowdownType::HOLDEM:
                    score = evaluate_holdem_high(hole, board_mask);
                    break;

                case ShowdownType::OMAHA:
                    score = evaluate_omaha_high(hole, board_mask);
                    break;

                case ShowdownType::MAKE5:
                    score = evaluate_make5_high(hole, board_mask);
                    break;

                case ShowdownType::DRAW:
                    score = evaluate_draw_high(hole);
                    break;

                default:
                    score = 0;
            }
        }

        results.push_back(std::vector<int>{score});
    }
    
    return results;
}