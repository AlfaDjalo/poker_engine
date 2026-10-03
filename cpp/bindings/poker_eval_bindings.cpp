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

// Defined in evaluator/equity_mc.cpp
std::vector<int64_t> holdem_matchup_counts(
    uint64_t hole_a,
    uint64_t hole_b,
    uint64_t board_mask,
    int n_samples,
    uint64_t seed
);

std::vector<std::vector<int64_t>> holdem_matchup_counts_batch(
    const std::vector<uint64_t>& holes_a,
    const std::vector<uint64_t>& holes_b,
    const std::vector<uint64_t>& boards,
    int n_samples,
    uint64_t seed
);

PYBIND11_MODULE(poker_eval, m)
{
    py::enum_<ScoreType>(m, "ScoreType", py::module_local())
        .value("HIGH", ScoreType::HIGH)
        .value("LOW_A5", ScoreType::LOW_A5)
        .value("LOW_27", ScoreType::LOW_27)
        .value("BADUGI", ScoreType::BADUGI);

    py::enum_<ShowdownType>(m, "ShowdownType", py::module_local())
        .value("HOLDEM", ShowdownType::HOLDEM)
        .value("OMAHA", ShowdownType::OMAHA)
        .value("MAKE5", ShowdownType::MAKE5)
        .value("DRAW", ShowdownType::DRAW)
        .value("BADUGI", ShowdownType::BADUGI);

    m.def("evaluate_hands", &evaluate_hands);

    m.def("holdem_matchup_counts", &holdem_matchup_counts,
          py::arg("hole_a"), py::arg("hole_b"), py::arg("board_mask"),
          py::arg("n_samples") = 200, py::arg("seed") = 12345,
          py::call_guard<py::gil_scoped_release>(),
          "Heads-up hold'em runout counts [a_wins, ties, b_wins]. Exact "
          "enumeration when <=2 board cards are missing, otherwise "
          "n_samples random runouts.");

    m.def("holdem_matchup_counts_batch", &holdem_matchup_counts_batch,
          py::arg("holes_a"), py::arg("holes_b"), py::arg("boards"),
          py::arg("n_samples") = 200, py::arg("seed") = 12345,
          py::call_guard<py::gil_scoped_release>(),
          "Batched holdem_matchup_counts: one [a_wins, ties, b_wins] per matchup.");
}