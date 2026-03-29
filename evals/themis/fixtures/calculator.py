"""A calculator module for evaluation of test-writing skills."""

from __future__ import annotations


class Calculator:
    """A chainable calculator with basic arithmetic operations."""

    def __init__(self, value: float = 0.0) -> None:
        self._value = value
        self._history: list[str] = []

    @property
    def value(self) -> float:
        return self._value

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def add(self, n: float) -> Calculator:
        self._history.append(f"add({n})")
        self._value += n
        return self

    def subtract(self, n: float) -> Calculator:
        self._history.append(f"subtract({n})")
        self._value -= n
        return self

    def multiply(self, n: float) -> Calculator:
        self._history.append(f"multiply({n})")
        self._value *= n
        return self

    def divide(self, n: float) -> Calculator:
        if n == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        self._history.append(f"divide({n})")
        self._value /= n
        return self

    def reset(self) -> Calculator:
        self._value = 0.0
        self._history.clear()
        return self
