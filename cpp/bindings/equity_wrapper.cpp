// equity_wrapper.cpp
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "omaha_equity.h"
#include <vector>
#include <string>

namespace py = pybind11;
using namespace omp;

// Wrapper function that returns a dict with detailed results
py::dict compute_equity(
    const std::vector<std::vector<std::string>>& hands,
    const std::vector<std::string>& board = std::vector<std::string>(),
    bool exact = true,
    uint64_t monte_carlo_samples = 100000,
    bool debug = false)
{
    OmahaEquityResults results = compute_omaha_equity(
        hands, board, exact, monte_carlo_samples, debug
    );
    
    py::dict output;
    output["equities"] = results.equity;
    output["wins"] = results.wins;
    output["ties"] = results.ties;
    output["total_hands"] = results.total_hands;
    output["exact"] = results.exact_calculation;
    
    return output;
}

// Python bindings
PYBIND11_MODULE(equity_wrapper, m) {
    m.doc() = "Omaha equity calculator using OMPEval";

    m.def("compute_equity", &compute_equity,
          py::arg("hands"),
          py::arg("board") = std::vector<std::string>(),
          py::arg("exact") = true,
          py::arg("monte_carlo_samples") = 100000,
          py::arg("debug") = false,
          "Compute Omaha equities for given hands and board.\n\n"
          "Args:\n"
          "  hands: List of player hands, each hand is a list of card strings\n"
          "         (e.g. [['As','Kd','Qh','Jc'], ['2h','3h','4h','5h']])\n"
          "  board: List of board card strings (0-5 cards)\n"
          "  exact: If True, use exact enumeration; if False, use Monte Carlo\n"
          "  monte_carlo_samples: Number of samples for Monte Carlo (ignored if exact=True)\n"
          "  debug: Print debug info to stdout\n\n"
          "Returns:\n"
          "  Dictionary with keys:\n"
          "    'equities': List of equity values (0-1) for each player\n"
          "    'wins': List of win counts for each player\n"
          "    'ties': List of tie counts (adjusted for split size)\n"
          "    'total_hands': Total number of hands evaluated\n"
          "    'exact': Boolean indicating if exact calculation was used");
}
