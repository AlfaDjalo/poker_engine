from enum import Enum, auto

class ActionType(Enum):
    FOLD = auto()
    CHECK = auto()
    CALL = auto()
    
    BET = auto()
    RAISE = auto()
