from __future__ import annotations


def query_rows_by_id_batches(db, statement, id_column, ids, *, scalars=False):
    """Read disjoint ID groups without expanding one large SQL parameter list.

    Aggregated statements must group by this ID so every group stays entirely
    within one batch. Keep all other filters on the supplied statement.
    """
    unique_ids = list(dict.fromkeys(ids))
    for offset in range(0, len(unique_ids), 1000):
        result = db.execute(statement.where(id_column.in_(unique_ids[offset:offset + 1000])))
        if scalars:
            result = result.scalars()
        yield from result.all()
