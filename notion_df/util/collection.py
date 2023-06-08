from __future__ import annotations

from enum import Enum
from typing import TypeVar, NewType

from notion_df.util.exception import NotionDfKeyError


class StrEnum(str, Enum):
    @property
    def value(self) -> str:
        return self._value_


Keychain = NewType('Keychain', tuple[str, ...])

KT = TypeVar('KT')
VT = TypeVar('VT')


class FinalDict(dict[KT, VT]):
    """dictionary which raises KeyError if trying to overwrite existing value."""

    def __setitem__(self, k: KT, v: VT) -> None:
        if cv := self.get(k):
            raise NotionDfKeyError('cannot overwrite FinalDict',
                                   {'key': k, 'new_value': v, 'current_value': cv})
        super().__setitem__(k, v)


class FinalClassDict(dict[KT, VT]):
    """dictionary which raises KeyError if trying to overwrite existing value.
    however if the new value is subclass of current value, error would not be raised.
    this is useful when you try to register a static class attributes as a mapping."""

    def __setitem__(self, k: KT, v: VT) -> None:
        if cv := self.get(k):
            if issubclass(v, cv):
                return
            raise NotionDfKeyError('cannot overwrite FinalDict',
                                   {'key': k, 'new_value': v, 'current_value': cv})
        super().__setitem__(k, v)


class DictFilter:
    @staticmethod
    def truthy(d: dict[KT, VT]) -> dict[KT, VT]:
        return {k: v for k, v in d.items() if v}

    @staticmethod
    def not_none(d: dict[KT, VT]) -> dict[KT, VT]:
        return {k: v for k, v in d.items() if v is not None}
