from abc import ABCMeta
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from notion_df2.core.serializable import TypeBasedDispatcher, DualSerializable
from notion_df.core.serialization import serialize_datetime


class Icon(DualSerializable, metaclass=ABCMeta):
    ...


_icon_dp = TypeBasedDispatcher(Icon)


@_icon_dp.register("emoji")
@dataclass
class Emoji(Icon):
    """https://developers.notion.com/reference/emoji-object"""
    value: str

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value})"

    def __str__(self) -> str:
        return self.value

    def serialize(self):
        return {"type": "emoji", "emoji": self.value}

    @classmethod
    def _deserialize(cls, data: dict[str, Any]) -> Self:
        return cls(data["emoji"])


class File(Icon, metaclass=ABCMeta):
    """https://developers.notion.com/reference/file-object"""


_file_dp = TypeBasedDispatcher(File, [_icon_dp])


@_file_dp.register("file")
@dataclass
class InternalFile(Icon):
    url: str
    expiry_time: datetime

    def serialize(self):
        return {
            "type": "file",
            "file": {"url": self.url, "expiry_time": serialize_datetime(self.expiry_time)},
        }

    @classmethod
    def _deserialize(cls, data: dict[str, Any]) -> Self:
        return cls(data["file"]["url"], data["file"]["expiry_time"])


@_file_dp.register("external")
@dataclass
class ExternalFile(Icon):
    url: str
    name: str

    def serialize(self):
        return {"type": "external", "name": self.name, "external": {"url": self.url}}

    @classmethod
    def _deserialize(cls, data: dict[str, Any]) -> Self:
        return cls(data["external"]["url"], "")
