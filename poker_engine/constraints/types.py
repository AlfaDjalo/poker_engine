from typing import NewType

NodeMask = int
NodeIndex = int

def bit(i: NodeIndex) -> NodeMask:
    if i < 0 or i>= 16:
        raise ValueError("Node index must be in [0, 15]")
    return 1 << i