from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from typing import Generic, Iterator, Optional, TypeVar

from typing_extensions import Self

from notion_df.core.serialization import DualSerializable, serialize_datetime, deserialize_datetime
from notion_df.object.constant import BlockColor, OptionColor
from notion_df.util.exception import NotionDfKeyError
from notion_df.util.misc import get_generic_element_type

_VT = TypeVar('_VT')


@dataclass
class Property(DualSerializable, metaclass=ABCMeta):
    name: str
    id: str = field(init=False, default=None)


Property_T = TypeVar('Property_T', bound=Property)


class Properties(DualSerializable, Generic[Property_T]):
    by_id: dict[str, Property_T]
    by_name: dict[str, Property_T]
    _property_type: type[Property_T]

    def __init__(self, props: Iterable[Property_T] = ()):
        self.by_id = {}
        self.by_name = {}
        for prop in props:
            self.add(prop)

    def serialize(self) -> dict[str, Property_T]:
        return self.by_name

    def __init_subclass__(cls, **kwargs):
        cls._property_type = get_generic_element_type(cls, cast_type=Property)

    def __repr__(self):
        return f'{type(self).__name__}({set(self.by_name.keys())})'

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, dict[str, Any]]) -> Self:
        properties = cls()
        for prop_name, prop_serialized in serialized.items():
            properties.add(cls._property_type.deserialize(prop_serialized))
        return properties

    def __iter__(self) -> Iterator[Property_T]:
        return iter(self.by_id.values())

    def __getitem__(self, key: str | Property_T) -> Property_T:
        if isinstance(key, str):
            if key in self.by_id:
                return self.by_id[key]
            return self.by_name[key]
        if isinstance(key, Property):
            return self.by_name[key.name]
        raise NotionDfKeyError('bad key', {'key': key})

    def __delitem__(self, key: str | Property_T) -> None:
        self.pop(self[key])

    def get(self, key: str | Property_T) -> Optional[Property_T]:
        try:
            return self[key]
        except KeyError:
            return None

    def add(self, prop: Property_T) -> None:
        self.by_id[prop.id] = prop
        self.by_name[prop.name] = prop

    def pop(self, prop: Property_T) -> Property_T:
        self.by_name.pop(prop.name)
        return self.by_id.pop(prop.id)


@dataclass
class Annotations(DualSerializable):
    bold: bool = False
    italic: bool = False
    strikethrough: bool = False
    underline: bool = False
    code: bool = False
    color: BlockColor = BlockColor.DEFAULT

    def serialize(self) -> dict[str, Any]:
        return self._serialize_as_dict()

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        return cls._deserialize_from_dict(serialized)


icon_registry: dict[str, type[Icon]] = {}


class Icon(DualSerializable, metaclass=ABCMeta):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if typename := cls.get_typename():
            icon_registry[typename] = cls

    @classmethod
    @abstractmethod
    def get_typename(cls) -> str:
        pass

    @classmethod
    def deserialize(cls, serialized: dict[str, Any]) -> Self:
        if cls != Icon:
            return cls._deserialize_this(serialized)
        subclass = icon_registry[serialized['type']]
        return subclass.deserialize(serialized)


@dataclass
class Emoji(Icon):
    # https://developers.notion.com/reference/emoji-object
    emoji: str

    @classmethod
    def get_typename(cls) -> str:
        return 'emoji'

    def serialize(self):
        return {
            "type": "emoji",
            "emoji": self.emoji
        }

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['emoji'])


@dataclass
class DateRange(DualSerializable):
    # timezone option is disabled. you should handle timezone inside 'start' and 'end'.
    start: datetime
    end: datetime

    def serialize(self):
        return {
            'start': serialize_datetime(self.start),
            'end': serialize_datetime(self.end),
        }

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        return cls(deserialize_datetime(serialized['start']), deserialize_datetime(serialized['end']))


@dataclass
class SelectOption(DualSerializable):
    name: str
    id: str = field(init=False, default=None)
    """Identifier of the option, which does not change if the name is changed. 
    These are sometimes, but not always, UUIDs."""
    color: OptionColor = field(init=False, default=None)

    def serialize(self) -> dict[str, Any]:
        return self._serialize_as_dict()

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        return cls._deserialize_from_dict(serialized)


@dataclass
class StatusGroups(DualSerializable):
    name: str
    id: str = field(init=False, default=None)
    """Identifier of the option, which does not change if the name is changed. 
    These are sometimes, but not always, UUIDs."""
    color: OptionColor = field(init=False, default=None)
    option_ids: list[str] = field()
    """Sorted list of ids of all options that belong to a group."""

    def serialize(self) -> dict[str, Any]:
        return self._serialize_as_dict()

    @classmethod
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        return cls._deserialize_from_dict(serialized)
