from .exceptions import NoPath
from .shortest_paths.unweighted import bidirectional_shortest_path_length
import os
import sys
import json
import time
import jose

__all__ = ["efficiency"]


def efficiency(G, u, v):
    try:
        eff = 1 / bidirectional_shortest_path_length(G, u, v)
    except NoPath:
        eff = 0
    return eff
