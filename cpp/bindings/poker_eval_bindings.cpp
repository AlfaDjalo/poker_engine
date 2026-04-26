#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../evaluator/score_types.hpp"

namespace py = pybind11;

std::vector<std::vector<int64_t>> evaluate_hands(
    const std::vector<uint64_t>& hole_masks,
    uint64_t board_mask,
    ScoreType score_type,
    ShowdownType showdown_type
);

PYBIND11_MODULE(poker_eval, m)
{
    py::enum_<ScoreType>(m, "ScoreType")
        .value("HIGH", ScoreType::HIGH)
        .value("LOW_A5", ScoreType::LOW_A5)
        .value("LOW_27", ScoreType::LOW_27)
        .value("BADUGI", ScoreType::BADUGI);

    py::enum_<ShowdownType>(m, "ShowdownType")
        .value("HOLDEM", ShowdownType::HOLDEM)
        .value("OMAHA", ShowdownType::OMAHA)
        .value("MAKE5", ShowdownType::MAKE5)
        .value("DRAW", ShowdownType::DRAW)
        .value("BADUGI", ShowdownType::BADUGI);

    m.def("evaluate_hands", &evaluate_hands);
}