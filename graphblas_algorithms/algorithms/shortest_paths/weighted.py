import numpy as np
from graphblas import Matrix, Vector, binary, monoid, replace, select, unary
from graphblas.semiring import any_pair, min_plus

from .._bfs import _bfs_level, _bfs_levels
from ..exceptions import Unbounded

__all__ = [
    "single_source_bellman_ford_path_length",
    "bellman_ford_path_lengths",
    "negative_edge_cycle",
]


def single_source_bellman_ford_path_length(G, source, *, cutoff=None):
    # No need for `is_weighted=` keyword, b/c this is assumed to be weighted (I think)
    index = G._key_to_id[source]
    if G.get_property("is_iso"):
        # If the edges are iso-valued (and positive), then we can simply do level BFS
        is_negative, iso_value = G.get_properties("has_negative_edges+ iso_value")
        if not is_negative:
            if cutoff is not None:
                cutoff = int(cutoff // iso_value)
            d = _bfs_level(G, source, cutoff, dtype=iso_value.dtype)
            if iso_value != 1:
                d *= iso_value
            return d
        # It's difficult to detect negative cycles with BFS
        if G._A[index, index].get() is not None:
            raise Unbounded("Negative cycle detected.")
        if not G.is_directed() and G._A[index, :].nvals > 0:
            # For undirected graphs, any negative edge is a cycle
            raise Unbounded("Negative cycle detected.")

    # Use `offdiag` instead of `A`, b/c self-loops don't contribute to the result,
    # and negative self-loops are easy negative cycles to avoid.
    # We check if we hit a self-loop negative cycle at the end.
    A, has_negative_diagonal = G.get_properties("offdiag has_negative_diagonal")
    if A.dtype == bool:
        # Should we upcast e.g. INT8 to INT64 as well?
        dtype = int
    else:
        dtype = A.dtype
    n = A.nrows
    d = Vector(dtype, n, name="single_source_bellman_ford_path_length")
    d[index] = 0
    cur = d.dup(name="cur")
    mask = Vector(bool, n, name="mask")
    one = unary.one[bool]
    for _i in range(n - 1):
        # This is a slightly modified Bellman-Ford algorithm.
        # `cur` is the current frontier of values that improved in the previous iteration.
        # This means that in this iteration we drop values from `cur` that are not better.
        cur << min_plus(cur @ A)
        if cutoff is not None:
            cur << select.valuele(cur, cutoff)

        # Mask is True where cur not in d or cur < d
        mask << one(cur)
        mask(binary.second) << binary.lt(cur & d)

        # Drop values from `cur` that didn't improve
        cur(mask.V, replace) << cur
        if cur.nvals == 0:
            break
        # Update `d` with values that improved
        d(cur.S) << cur
    else:
        # Check for negative cycle when for loop completes without breaking
        cur << min_plus(cur @ A)
        if cutoff is not None:
            cur << select.valuele(cur, cutoff)
        mask << binary.lt(cur & d)
        if mask.reduce(monoid.lor):
            raise Unbounded("Negative cycle detected.")
    if has_negative_diagonal:
        # We removed diagonal entries above, so check if we visited one with a negative weight
        diag = G.get_property("diag")
        cur << select.valuelt(diag, 0)
        if any_pair(d @ cur):
            raise Unbounded("Negative cycle detected.")
    return d


def bellman_ford_path_lengths(G, nodes=None, *, expand_output=False):
    """Extra parameter: expand_output

    Parameters
    ----------
    expand_output : bool, default False
        When False, the returned Matrix has one row per node in nodes.
        When True, the returned Matrix has the same shape as the input Matrix.
    """
    # Same algorithms as in `single_source_bellman_ford_path_length`, but with
    # `Cur` as a Matrix with each row corresponding to a source node.
    if G.get_property("is_iso"):
        is_negative, iso_value = G.get_properties("has_negative_edges+ iso_value")
        if not is_negative:
            D = _bfs_levels(G, nodes, dtype=iso_value.dtype)
            if iso_value != 1:
                D *= iso_value
            if nodes is not None and expand_output and D.ncols != D.nrows:
                ids = G.list_to_ids(nodes)
                rv = Matrix(D.dtype, D.ncols, D.ncols, name=D.name)
                rv[ids, :] = D
                return rv
            return D
        if not G.is_directed():
            # For undirected graphs, any negative edge is a cycle
            if nodes is not None:
                ids = G.list_to_ids(nodes)
                if G._A[ids, :].nvals > 0:
                    raise Unbounded("Negative cycle detected.")
            elif G._A.nvals > 0:
                raise Unbounded("Negative cycle detected.")

    A, has_negative_diagonal = G.get_properties("offdiag has_negative_diagonal")
    if A.dtype == bool:
        dtype = int
    else:
        dtype = A.dtype
    n = A.nrows
    if nodes is None:
        # TODO: `D = Vector.from_scalar(0, n, dtype).diag()`
        D = Vector(dtype, n, name="bellman_ford_path_lengths_vector")
        D << 0
        D = D.diag(name="bellman_ford_path_lengths")
    else:
        ids = G.list_to_ids(nodes)
        D = Matrix.from_coo(
            np.arange(len(ids), dtype=np.uint64),
            ids,
            0,
            dtype,
            nrows=len(ids),
            ncols=n,
            name="bellman_ford_path_lengths",
        )
    Cur = D.dup(name="Cur")
    Mask = Matrix(bool, D.nrows, D.ncols, name="Mask")
    one = unary.one[bool]
    for _i in range(n - 1):
        Cur << min_plus(Cur @ A)
        Mask << one(Cur)
        Mask(binary.second) << binary.lt(Cur & D)
        Cur(Mask.V, replace) << Cur
        if Cur.nvals == 0:
            break
        D(Cur.S) << Cur
    else:
        Cur << min_plus(Cur @ A)
        Mask << binary.lt(Cur & D)
        if Mask.reduce_scalar(monoid.lor):
            raise Unbounded("Negative cycle detected.")
    if has_negative_diagonal:
        diag = G.get_property("diag")
        cur = select.valuelt(diag, 0)
        if any_pair(D @ cur).nvals > 0:
            raise Unbounded("Negative cycle detected.")
    if nodes is not None and expand_output and D.ncols != D.nrows:
        rv = Matrix(D.dtype, n, n, name=D.name)
        rv[ids, :] = D
        return rv
    return D


def negative_edge_cycle(G):
    # TODO: use a heuristic to try to stop early
    if G.is_directed():
        deg = "total_degrees-"
    else:
        deg = "degrees-"
    A, degrees, has_negative_diagonal, has_negative_edges = G.get_properties(
        f"offdiag {deg} has_negative_diagonal has_negative_edges-"
    )
    if has_negative_diagonal:
        return True
    if not has_negative_edges:
        return False
    if A.dtype == bool:
        # Should we upcast e.g. INT8 to INT64 as well?
        dtype = int
    else:
        dtype = A.dtype
    n = A.nrows
    # Begin from every node that has edges
    d = Vector(dtype, n, name="negative_edge_cycle")
    d(degrees.S) << 0
    cur = d.dup(name="cur")
    mask = Vector(bool, n, name="mask")
    one = unary.one[bool]
    for _i in range(n - 1):
        cur << min_plus(cur @ A)
        mask << one(cur)
        mask(binary.second) << binary.lt(cur & d)
        cur(mask.V, replace) << cur
        if cur.nvals == 0:
            return False
        d(cur.S) << cur
    cur << min_plus(cur @ A)
    mask << binary.lt(cur & d)
    if mask.reduce(monoid.lor):
        return True
    return False
