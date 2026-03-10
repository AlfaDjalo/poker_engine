#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../cards/card_utils.h"

namespace py = pybind11;

PYBIND11_MODULE(poker_cards, m)
{
    using namespace cards;

    m.def("card_to_mask", &card_to_mask);

    m.def("cards_to_mask", &cards_to_mask);

    m.def("mask_to_cards", &mask_to_cards);

    m.def("popcount", &popcount);
}
