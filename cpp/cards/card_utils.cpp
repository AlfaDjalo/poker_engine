#include "card_utils.h"
#include <stdexcept>

namespace cards {
    int rank_index(char r)
    {
        switch(r)
        {
            case '2': return 0;
            case '3': return 1;
            case '4': return 2;
            case '5': return 3;
            case '6': return 4;
            case '7': return 5;
            case '8': return 6;
            case '9': return 7;
            case 'T': return 8;
            case 'J': return 9;
            case 'Q': return 10;
            case 'K': return 11;
            case 'A': return 12;
        }

        throw std::runtime_error("Invalid rank");
    }

    int suit_index(char s)
    {
        switch(s)
        {
            case 'c': return 0;
            case 'd': return 1;
            case 'h': return 2;
            case 's': return 3;
        }

        throw std::runtime_error("Invalid suit");
    }

    CardMask card_to_mask(const std::string& card)
    {
        if(card.size() != 2)
            throw std::runtime_error("Invalid card");

        int r = rank_index(card[0]);
        int s = suit_index(card[1]);

        int bit = s * 13 + r;

        return (CardMask(1) << bit);
    }

    CardMask cards_to_mask(const std::vector<std::string>& cards)
    {
        CardMask mask = 0;

        for (const auto& c : cards)
            mask |= card_to_mask(c);

        return mask;
    }

    std::vector<std::string> mask_to_cards(CardMask mask)
    {
        std::vector<std::string> result;

        static const char ranks[] = {
            '2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'
        };

        static const char suit[] = {'c', 'd', 'h', 's'};

        for (int bit = 0; bit < 52; bit++)
        {
            if (mask & (CardMask(1) << bit))
            {
                int suit = bit / 13;
                int rank = bit % 13;

                std::string card;
                card += ranks[rank];
                card += suits[suit];

                result.push_back(card);
            }
        }

        return result;
    }

    int popcount(CardMask mask)
    {
        return __builtin_popcountll(mask);
    }
}