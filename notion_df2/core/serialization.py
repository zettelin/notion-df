from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from inspect import isclass
from types import NoneType, UnionType
from typing import (
    Any,
    Literal,
    TypeVar,
    Union,
    get_args,
    get_origin,
    overload,
)
from uuid import UUID

import dateutil.parser
from loguru import logger

from notion_df.core.variable import my_tz
from notion_df2.core.serializable import Deserializable, Serializable

T = TypeVar("T")
_UNSUPPORTED_TYPE_MSG = "Unsupported type"


def serialize(obj: Any) -> Any:
    """unified serializer for both Serializable and external classes."""
    return _serialize(obj, path=[])


def _serialize(obj: Any, path: list[str]) -> Any:
    if obj is None:
        return None
    if isinstance(obj, bool | str | int | float):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v, path + [k]) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_serialize(e, path + [i]) for i, e in enumerate(obj)]
    if isinstance(obj, set):
        return [_serialize(e, path + [-1]) for e in obj]
    if isinstance(obj, Serializable):
        try:
            return obj.serialize()
        except SerializationError as e:
            raise SerializationError(e.err, obj, path + e.path)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return serialize_datetime(obj, path)
    if isinstance(obj, date):
        return serialize_date(obj, path)
    if isinstance(obj, UUID):
        return str(obj)
    raise SerializationError(_UNSUPPORTED_TYPE_MSG, obj, path)


@overload
def deserialize(obj: Any, tp: type[T]) -> T: ...


@overload
def deserialize(obj: Any, tp: type[T] | None) -> T | None: ...


@overload
def deserialize(obj: Any, tp: type) -> Any: ...


def deserialize(obj: Any, tp: type[T]) -> T:
    """unified deserializer for both Deserializable and external classes."""
    return _deserialize(obj, tp, path=[])


def _deserialize(obj: Any, tp: type, path: list[str]) -> Any:
    if isclass(tp):
        return _deserialize_class_type(obj, tp, path)
    else:
        return _deserialize_non_class_type(obj, tp, path)


def _deserialize_class_type(obj: Any, tp: type, path: list[str]) -> Any:
    if issubclass(tp, bool | str | int | float | Decimal | Enum | UUID):
        try:
            return tp(obj)
        except (TypeError, ValueError) as e:
            raise DeserializationError(e, obj, tp, path)
    if issubclass(tp, Deserializable):
        try:
            return tp.deserialize(obj)
        except DeserializationError as e:
            raise DeserializationError(e.err, obj, tp, path + e.path)
    if issubclass(tp, dict | list | set | tuple):
        raise DeserializationError("Collection types require explicit value types", obj, tp, path)
    if issubclass(tp, datetime):
        return deserialize_datetime(obj, path)
    if issubclass(tp, date):
        return deserialize_date(obj, path)
    raise DeserializationError(
        _UNSUPPORTED_TYPE_MSG, obj, tp, path
    )


def _deserialize_non_class_type(obj: Any, tp: type, path: list[str]) -> Any:
    origin = get_origin(tp)
    args = get_args(tp)
    if tp is Any:
        return obj
    if is_newtype(tp):
        return tp(_deserialize(obj, getattr(tp, "__supertype__"), path))
    elif origin is Literal:
        if obj in args:
            return obj
        raise DeserializationError(
            "Serialized value does not match any of Literal types",
            obj, tp, path
        )
    elif origin in [Union, UnionType]:
        if typ == int | float:
            assert isinstance(obj, int | float), DeserializationError("Not a number", obj, tp, path)
            return obj
        try:
            inner_type, = [
                arg for arg in args if arg is not NoneType
            ]
        except ValueError:
            raise DeserializationError(
                "Union type except Optionals are not supported. Create a common base class instead.",
                obj, tp, path
            )
        return _deserialize(obj, inner_type, path) if obj is not None else None
    elif issubclass(origin, dict):
        ret = {}
        assert isinstance(obj, dict), DeserializationError(
            "Origin is dict but obj is not dict", obj, tp, path
        )
        try:
            key_type, value_type = args
        except TypeError:
            raise DeserializationError(
                "Dictionary type requires exactly two type arguments", obj, tp, path
            )
        for key, value in obj.items():
            try:
                ret[key_type(key)] = _deserialize(value, value_type, path + [key])
            except DeserializationError as e:
                raise DeserializationError(e.err, obj, tp, path + e.path)
        return origin(ret)
    elif issubclass(origin, list | set | tuple):
        ret = []
        assert isinstance(obj, list), DeserializationError(
            "Origin is list/set/tuple but obj is not list", obj, tp, path
        )
        try:
            value_type = args[0]
        except IndexError:
            raise DeserializationError(
                "List type requires exactly one type argument", obj, tp, path
            )
        for i, value in enumerate(obj):
            try:
                ret.append(_deserialize(value, value_type, path + [i]))
            except DeserializationError as e:
                raise DeserializationError(e.err, obj, tp, path + e.path)
        return origin(ret)
    raise DeserializationError(
        _UNSUPPORTED_TYPE_MSG, obj, tp, path
    )


def is_newtype(tp: object) -> bool:
    return (
        callable(tp)
        and hasattr(tp, "__supertype__")
        and tp.__module__ == "typing"
        and tp.__name__ != "NewType"
    )


class SerializationError(Exception):
    def __init__(self, err: str | Exception, obj: Any, path: list[str]):
        super().__init__(err)
        self.err: Exception = err if isinstance(err, Exception) else Exception(err)
        self.obj = obj
        self.path = path

    def __repr__(self) -> str:
        return f"{type(self).__name__}(err={self.err}, obj={self.obj}, path={self.path})"


class DeserializationError(Exception):
    def __init__(self, err: str | Exception, obj: Any, tp: type | Any, path: list[str]):
        super().__init__(err)
        self.err: Exception = err if isinstance(err, Exception) else Exception(err)
        self.obj = obj
        self.tp = tp
        self.path = path

    def __repr__(self) -> str:
        return f"{type(self).__name__}(err={self.err}, obj={self.obj}, tp={self.tp}, path={self.path})"


def serialize_date(dt: date, path: list[str]) -> str:
    if not isinstance(dt, date):
        raise SerializationError("Not a date type", dt, path)
    return dt.isoformat()


def serialize_datetime(dt: datetime, path: list[str]) -> str:
    if not isinstance(dt, datetime):
        raise SerializationError("Not a datetime type", dt, path)
    dt = dt.replace(tzinfo=my_tz).astimezone(my_tz)
    return dt.isoformat()


def deserialize_date(obj: str, path: list[str]) -> date:
    try:
        dt = dateutil.parser.parse(obj)
    except dateutil.parser.ParserError as e:
        print(obj)
        raise DeserializationError(e, obj, date, path)
    return dt.date()


def deserialize_datetime(obj: str, path: list[str]) -> datetime:
    try:
        dt = dateutil.parser.parse(obj)
    except dateutil.parser.ParserError as e:
        print(obj)
        raise DeserializationError(e, obj, datetime, path)
    return dt.astimezone(my_tz)
