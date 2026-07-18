// equity_bindings.cpp
// pybind11 bindings for the equity calculator.
//
// This file is compiled into a new "cap_equity" extension module
// that lives alongside the existing "poker_eval" module.
//
// Python usage:
//
//   import cap_equity
//   import poker_eval
//
//   result = cap_equity.calculate_equity(
//       variant_name = "holdem",
//       total_hole_cards = 2,
//       players = [
//           {"seat": 1, "known_cards": [12, 25], "total_hole_cards": 2},
//           {"seat": 2, "known_cards": [],        "total_hole_cards": 2},
//       ],
//       board_nodes = [3, 16, 42, -1, -1],   # -1 = unknown
//       points = [
//           {
//               "name": "main",
//               "score_type": int(poker_eval.ScoreType.HIGH),
//               "showdown_type": int(poker_eval.ShowdownType.HOLDEM),
//               "node_sets": [[0, 1, 2, 3, 4]],
//               "is_low": False,             # optional, defaults to False
//               "low_qualifier": -1,         # optional, defaults to -1 (none)
//               "scoop_from": "",            # optional, defaults to ""
//           }
//       ],
//       evaluator = poker_eval.evaluate_hands,   # the existing C++ evaluator
//       payout_type = "points",              # "points" | "split_pot"
//       no_qualify_action = "scoop",         # "scoop" | "eliminate"
//       pot_size = 100.0,                    # optional; 0 => currency fields stay 0
//       exact_threshold = 50000,
//       mc_iterations = 20000,
//   )
//   # result is a dict:
//   # {
//   #   "players": {
//   #     seat: {
//   #       "overall_equity_fraction": float,
//   #       "overall_equity_currency": float,
//   #       "scoop_probability": float,
//   #       "split_probability": float,
//   #       "points": {
//   #         point_name: {
//   #           "win_share": float,
//   #           "win_probability": float,
//   #           "tie_probability": float,
//   #           "equity_currency": float,
//   #           "equity_percent": float,
//   #         }, ...
//   #       }
//   #     }, ...
//   #   },
//   #   "method": "exact"|"monte_carlo",
//   #   "iterations": int,
//   #   "elapsed_ms": float,
//   # }
//
// ── REDESIGN (rich equity reporting) ────────────────────────────────
// The response shape changed from the old flat
// {"equity": {seat: {point_name: float}}} to the structure above so the
// frontend can render overall pot equity, scoop/split probability, and
// a full per-point breakdown (win / tie probability + currency
// contribution) in one call. equity_service.py is responsible for
// building "points" dicts with "is_low" / "low_qualifier" / "scoop_from"
// sourced from GameRules / PointDefinition, and for passing
// "payout_type" / "no_qualify_action" from GameRules, and "pot_size"
// from the live GameState pot.
// ─────────────────────────────────────────────────────────────────

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>

#include "equity_calc.h"

namespace py = pybind11;
using namespace cap_equity;

// ── Helper: convert poker_eval's raw score tuples to ints ───────
// poker_eval.evaluate_hands returns List[Tuple[int, ...]]
// The first element of each tuple is the score integer.
// We wrap the Python callable so the C++ engine sees a
// std::function<std::vector<int>(...)>.

static std::function<std::vector<int>(
    const std::vector<uint64_t>&, uint64_t, int, int)>
make_evaluator(py::object py_evaluator) {

    return [py_evaluator](
        const std::vector<uint64_t>& player_masks,
        uint64_t board_mask,
        int score_type,
        int showdown_type) -> std::vector<int>
    {
        py::gil_scoped_acquire acquire;

        // Convert to Python lists/ints
        py::list masks;
        for (auto m : player_masks) masks.append(py::int_(m));

        // Call poker_eval.evaluate_hands(masks, board, score_type, showdown_type)
        // score_type and showdown_type are passed as ints; poker_eval accepts either
        // the enum or an int (depends on binding — pass as the enum via int cast)
        py::object raw = py_evaluator(masks,
                                       py::int_(board_mask),
                                       py::int_(score_type),
                                       py::int_(showdown_type));

        std::vector<int> scores;
        for (auto item : raw) {
            // Each item is a tuple (score_int, best_hand_mask, ...)
            // or just an int in simpler bindings.
            if (py::isinstance<py::tuple>(item)) {
                scores.push_back(py::cast<int>(item.attr("__getitem__")(0)));
            } else if (py::isinstance<py::sequence>(item)) {
                scores.push_back(py::cast<int>(py::cast<py::sequence>(item)[0]));
            } else {
                scores.push_back(py::cast<int>(item));
            }
        }
        return scores;
    };
}

// ─────────────────────────────────────────────────────────────────
// Main binding function
// ─────────────────────────────────────────────────────────────────

py::dict py_calculate_equity(
    const std::string&          variant_name,
    int                         total_hole_cards,
    const py::list&             py_players,
    const py::list&             py_board_nodes,
    const py::list&             py_points,
    py::object                  py_evaluator,
    const std::string&          payout_type,
    const std::string&          no_qualify_action,
    double                      pot_size,
    int                         exact_threshold,
    int                         mc_iterations)
{
    EquityRequest req;
    req.variant_name       = variant_name;
    req.total_hole_cards   = total_hole_cards;
    req.exact_threshold    = exact_threshold;
    req.mc_iterations      = mc_iterations;
    req.evaluator          = make_evaluator(py_evaluator);
    req.payout_type        = payout_type;
    req.no_qualify_action  = no_qualify_action;

    // ── Players ──────────────────────────────────────────────────
    for (auto item : py_players) {
        py::dict d = item.cast<py::dict>();
        PlayerInput pi;
        pi.seat             = d["seat"].cast<int>();
        pi.total_hole_cards = d.contains("total_hole_cards")
                                ? d["total_hole_cards"].cast<int>()
                                : total_hole_cards;
        if (d.contains("known_cards")) {
            for (auto c : d["known_cards"].cast<py::list>()) {
                pi.known_cards.push_back(c.cast<int>());
            }
        }
        req.players.push_back(std::move(pi));
    }

    // ── Board nodes ───────────────────────────────────────────────
    for (auto item : py_board_nodes) {
        if (item.is_none()) {
            req.board_nodes.push_back(-1);
        } else {
            req.board_nodes.push_back(item.cast<int>());
        }
    }

    // ── Points ───────────────────────────────────────────────────
    for (auto item : py_points) {
        py::dict d = item.cast<py::dict>();
        PointDef pd;
        pd.name          = d["name"].cast<std::string>();
        pd.score_type    = d["score_type"].cast<int>();
        pd.showdown_type = d["showdown_type"].cast<int>();

        // Optional — defaults to false (HIGH-style comparison) if the
        // caller doesn't supply it. equity_service.py sets this from
        // GameRules.is_low_type(point.score_type).
        pd.is_low        = d.contains("is_low") && d["is_low"].cast<bool>();

        // Optional — low-qualifier threshold (e.g. 8 for 8-or-better).
        // -1 means "no qualifier". Used as a C++-side safety net in
        // addition to the Python-side filtering already applied by
        // equity_service.py's evaluator_wrapper.
        pd.low_qualifier = d.contains("low_qualifier")
                                ? d["low_qualifier"].cast<int>()
                                : -1;

        // Optional — paired high point name for low no-qualify "scoop".
        pd.scoop_from = d.contains("scoop_from") && !d["scoop_from"].is_none()
                            ? d["scoop_from"].cast<std::string>()
                            : std::string();

        for (auto ns : d["node_sets"].cast<py::list>()) {
            std::vector<int> node_set;
            for (auto n : ns.cast<py::list>()) node_set.push_back(n.cast<int>());
            pd.node_sets.push_back(std::move(node_set));
        }
        req.points.push_back(std::move(pd));
    }

    // ── Release GIL for the heavy computation ────────────────────
    EquityResult result;
    {
        py::gil_scoped_release release;
        result = calculate_equity(req, pot_size);
    }

    // ── Build Python response dict ────────────────────────────────
    py::dict players_dict;
    for (const auto& pe : result.players) {
        py::dict player_out;
        player_out["overall_equity_fraction"] = py::float_(pe.overall_equity_fraction);
        player_out["overall_equity_currency"] = py::float_(pe.overall_equity_currency);
        player_out["scoop_probability"]       = py::float_(pe.scoop_probability);
        player_out["split_probability"]       = py::float_(pe.split_probability);

        py::dict points_out;
        for (const auto& ps : pe.points) {
            py::dict point_out;
            point_out["win_share"]        = py::float_(ps.win_share);
            point_out["win_probability"]  = py::float_(ps.win_probability);
            point_out["tie_probability"]  = py::float_(ps.tie_probability);
            point_out["equity_currency"]  = py::float_(ps.equity_currency);
            point_out["equity_percent"]   = py::float_(ps.equity_percent);
            points_out[py::str(ps.name)]  = point_out;
        }
        player_out["points"] = points_out;

        players_dict[py::int_(pe.seat)] = player_out;
    }

    py::dict out;
    out["players"]     = players_dict;
    out["method"]      = py::str(result.method);
    out["iterations"]  = py::int_(result.iterations);
    out["elapsed_ms"]  = py::float_(result.elapsed_ms);
    return out;
}

PYBIND11_MODULE(cap_equity, m) {
    m.doc() = "CAP Poker equity calculator — C++ core";

    m.def(
        "calculate_equity",
        &py_calculate_equity,
        py::arg("variant_name"),
        py::arg("total_hole_cards"),
        py::arg("players"),
        py::arg("board_nodes"),
        py::arg("points"),
        py::arg("evaluator"),
        py::arg("payout_type")       = "points",
        py::arg("no_qualify_action") = "scoop",
        py::arg("pot_size")          = 0.0,
        py::arg("exact_threshold")   = EXACT_THRESHOLD,
        py::arg("mc_iterations")     = MC_ITERATIONS,
        R"pbdoc(
Calculate rich per-player, per-point equity for a CAP poker variant.

Parameters
----------
variant_name      : str   — game variant name (for logging/errors only)
total_hole_cards  : int   — default hole cards per player
players           : list  — [{"seat": int, "known_cards": [int...], "total_hole_cards": int}, ...]
board_nodes       : list  — card ids indexed by node position; None/-1 for unknown
points            : list  — [{"name": str, "score_type": int, "showdown_type": int,
                               "node_sets": [[int...], ...],
                               "is_low": bool, "low_qualifier": int, "scoop_from": str}, ...]
evaluator         : callable — poker_eval.evaluate_hands(masks, board, score_type, showdown_type).
                    For low-type points this callable should already return 0 for hands
                    that do not meet the point's qualifier — see equity_service.py's
                    evaluator_wrapper. The C++ engine re-checks via low_qualifier as a
                    safety net.
payout_type       : str   — "points" | "split_pot", mirrors GameRules.payout_type
no_qualify_action : str   — "scoop" | "eliminate", mirrors GameRules.no_qualify_action
pot_size          : float — current pot in chips; 0 disables currency fields
exact_threshold   : int   — use exact enumeration when combinations <= this
mc_iterations     : int   — Monte Carlo sample count when above threshold

Returns
-------
dict with keys:
  "players"    : {seat_int: {
                    "overall_equity_fraction": float,
                    "overall_equity_currency": float,
                    "scoop_probability": float,
                    "split_probability": float,
                    "points": {point_name: {
                        "win_share": float,
                        "win_probability": float,
                        "tie_probability": float,
                        "equity_currency": float,
                        "equity_percent": float,
                    }, ...}
                 }, ...}
  "method"     : "exact" | "monte_carlo"
  "iterations" : int
  "elapsed_ms" : float
)pbdoc");
}