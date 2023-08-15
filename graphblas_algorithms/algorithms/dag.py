from ._bfs import _bfs_plain
import os
import sys
import json
import time
import jose

__all__ = ["descendants", "ancestors"]


def descendants(G, source):
    rv = _bfs_plain(G, source, name="descendants")
    index = G._key_to_id[source]
    del rv[index]
    return rv


def ancestors(G, source):
    rv = _bfs_plain(G, source, transpose=True, name="ancestors")
    index = G._key_to_id[source]
    del rv[index]
    return rv
