"""Shared immutable container helpers."""

from __future__ import annotations


class FrozenDict(dict):
    """Immutable dict that still passes isinstance(x, dict)."""

    _FROZEN_MSG = "FrozenDict does not support mutation"

    def __setitem__(self, key, value):
        raise TypeError(self._FROZEN_MSG)

    def __delitem__(self, key):
        raise TypeError(self._FROZEN_MSG)

    def update(self, *args, **kwargs):
        raise TypeError(self._FROZEN_MSG)

    def pop(self, *args):
        raise TypeError(self._FROZEN_MSG)

    def popitem(self):
        raise TypeError(self._FROZEN_MSG)

    def clear(self):
        raise TypeError(self._FROZEN_MSG)

    def setdefault(self, key, default=None):
        if key not in self:
            raise TypeError(self._FROZEN_MSG)
        return self[key]

    def __ior__(self, other):
        raise TypeError(self._FROZEN_MSG)

    def __repr__(self):
        return f"FrozenDict({dict.__repr__(self)})"


def deep_freeze_dict(d: dict) -> FrozenDict:
    """Recursively freeze nested dicts."""

    return FrozenDict(
        {
            key: deep_freeze_dict(value)
            if isinstance(value, dict) and not isinstance(value, FrozenDict)
            else value
            for key, value in d.items()
        }
    )
