from __future__ import annotations

import inspect
import re
import types
from abc import ABCMeta, abstractmethod
from dataclasses import fields, InitVar, Field, field, dataclass, is_dataclass
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from functools import cache

# noinspection PyUnresolvedReferences
from typing import (
    Any,
    get_origin,
    get_args,
    final,
    NewType,
    cast,
    get_type_hints,
    _GenericAlias,
    Union,
    Literal,
    TypeVar,
    overload,
)
from uuid import UUID

import dateutil.parser
from typing_extensions import Self

from notion_df.core.exception import NotionDfException, ImplementationError
from notion_df.core.variable import my_tz


@dataclass(kw_only=True)
class SerializationError(NotionDfException):
    description: str = field(default="")
    """instance-specific description"""
    err_vars: dict[str, Any] = field(default_factory=dict)
    """dumped variables in error log"""
    inverted_path: list[str | int] = field(default_factory=list)
    """inverted path to indicate nested location of error"""
    linebreak: bool = field(default=True)
    """whether or not to print one variable at a line"""

    def __post_init__(self) -> None:
        self.args: tuple[str, ...] = ()
        if self.description:
            self.args += (self.description,)
        if self.inverted_path:
            self.args += (self.inverted_path,)
        if self.err_vars:
            var_items_list = [f"{k} = {v}" for k, v in self.err_vars.items()]
            if self.linebreak:
                var_items_str = "[[\n" + "\n".join(var_items_list) + "\n]]"
            else:
                var_items_str = "[[ " + ", ".join(var_items_list) + " ]]"
            self.args += (var_items_str,)


def serialize(obj: Any):
    """unified serializer for both Serializable and external classes."""
    if obj is None:
        return None
    if isinstance(obj, Serializable):
        return obj.serialize()
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list) or isinstance(obj, set):
        return [serialize(e) for e in obj]
    if isinstance(obj, (bool, str, int, float)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, date):
        return serialize_datetime(obj)
    if isinstance(obj, UUID):
        return str(obj)
    raise SerializationError(description="Cannot serialize", err_vars={"obj": obj})


T = TypeVar("T")


@overload
def deserialize(typ: type[T], serialized: Any) -> T: ...


@overload
def deserialize(typ: type, serialized: Any) -> Any: ...


def deserialize(typ: type, serialized: Any) -> Any:
    """unified deserializer for both Deserializable and external classes."""
    err_vars = {"typ": typ, "serialized": serialized}
    typ_origin: type = get_origin(typ)
    typ_args = get_args(typ)

    # 0. explicitly unsupported values
    if typ is None or serialized is None or typ == Any:
        return serialized

    # 1. Non-class types
    if isinstance(typ, NewType):  # type: ignore
        plain_type = cast(NewType, typ).__supertype__
        return typ(deserialize(plain_type, serialized))
    if isinstance(typ, InitVar):
        return deserialize(typ.type, serialized)
    if typ_origin == Literal:
        if serialized in typ_args:
            return serialized
        raise SerializationError(
            description="Serialized value does not match any of Literal types",
            err_vars=err_vars,
        )
    if (
        isinstance(typ, types.UnionType) or typ_origin == Union
    ):  # also can handle Optional
        for typ_arg in typ_args:
            try:
                return deserialize(typ_arg, serialized)
            except SerializationError as e:
                err_vars.setdefault("exception_list", [])
                err_vars["exception_list"].append(e)
        raise SerializationError(
            description="Cannot deserialize to any of the UnionType", err_vars=err_vars
        )
    if isinstance(typ, types.GenericAlias) or isinstance(typ, _GenericAlias):
        err_vars.update({"typ.origin": typ_origin, "typ.args": typ_args})
        collection_type_error = SerializationError(
            description="Collection types require value type to be defined",
            err_vars=err_vars,
        )
        if issubclass(typ_origin, dict):
            try:
                value_type = typ_args[1]
            except IndexError:
                raise collection_type_error
            result = {}
            for key, value in cast(dict, serialized).items():
                try:
                    result[key] = deserialize(value_type, value)
                except SerializationError as e:
                    e.inverted_path.append(key)
                    raise e
                return typ_origin(result)
        if issubclass(typ_origin, list) or issubclass(typ_origin, set):
            try:
                value_type = typ_args[0]
            except IndexError:
                raise collection_type_error
            result = []
            for i, value in enumerate(cast(list, serialized)):
                try:
                    result.append(deserialize(value_type, value))
                except SerializationError as e:
                    e.inverted_path.append(i)
                    raise e
            return typ_origin(result)
        raise SerializationError(
            description="GenericAlias with invalid origin", err_vars=err_vars
        )
    if not inspect.isclass(typ):
        raise SerializationError(
            description="Unsupported non-class type", err_vars=err_vars
        )

    # 2. class types
    if issubclass(typ, Deserializable):
        if isinstance(serialized, Deserializable):
            return serialized
        return typ.deserialize(serialized)
    if typ in {bool, str, int, float, Decimal} or issubclass(typ, Enum):
        try:
            return typ(serialized)
        except (ValueError, TypeError) as e:
            err_vars["exception"] = e
            raise SerializationError(err_vars=err_vars)
    if typ == UUID:
        if isinstance(serialized, UUID):
            return serialized
        return UUID(serialized)
    if issubclass(typ, datetime):
        try:
            return deserialize_datetime(serialized)
        except (ValueError, TypeError) as e:
            err_vars["exception"] = e
            raise SerializationError(err_vars=err_vars)
    raise SerializationError(description="Unsupported class", err_vars=err_vars)


class Serializable(metaclass=ABCMeta):
    """representation of the resources defined in Notion REST API.
    can be dumped into JSON object."""

    @abstractmethod
    def serialize(self) -> Any:
        raise NotImplementedError

    @final
    def _serialize_as_dict(self, **overrides: Any) -> dict[str, Any]:
        """this can only be called from dataclasses.

        helper method to implement serialize().
        Note: this drops post-init fields."""
        assert is_dataclass(self)
        serialized = {}
        # noinspection PyDataclass
        for fd in fields(self):
            if not fd.init:
                continue
            fd_value = overrides.get(fd.name, getattr(self, fd.name))
            serialized[fd.name] = serialize(fd_value)
        return serialized


class Deserializable(metaclass=ABCMeta):
    """representation of the resources defined in Notion REST API.
    can be loaded from JSON object.
    Concrete classes should implement _deserialize_this();
    Abstract classes can implement _deserialize_this() and _deserialize_subclass()."""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__()
        if not inspect.isabstract(cls):
            # noinspection PyBroadException
            try:
                cls._deserialize_subclass(None)
            except NotImplementedError:
                pass
            except:  # noqa: E722 NOSONAR
                raise ImplementationError(
                    "_deserialize_subclass() should not be defined on concrete classes"
                )
        deserialize_subclass_old = cls._deserialize_subclass

        # noinspection PyDecorator
        @classmethod
        def deserialize_subclass_new(_cls: type[Self], raw: Any) -> Self:
            # cls: the base class _deserialize_subclass is defined
            # _cls: the subclass _deserialize_subclass is called
            if _cls != cls:
                raise NotImplementedError
            return deserialize_subclass_old(raw)

        cls._deserialize_subclass = deserialize_subclass_new

    @classmethod
    @final
    def deserialize(cls, raw: Any) -> Self:
        try:
            return cls._deserialize_subclass(raw)
        except NotImplementedError:
            return cls._deserialize_this(raw)

    @classmethod
    @abstractmethod
    def _deserialize_this(cls, raw: Any) -> Self:
        """Override this to deserialize itself and its subclasses."""
        raise NotImplementedError

    @classmethod
    def _deserialize_subclass(cls, raw: Any) -> Self:
        """Override this to deserialize its subclasses.
        only reachable from the defined class itself.
        prioritized over _deserialize_this().
        should NOT be defined on concrete classes."""
        raise NotImplementedError

    @classmethod
    @final
    def _deserialize_from_dict(
        cls, serialized: dict[str, Any], **overrides: Any
    ) -> Self:
        """this should only be called from dataclass.

        helper method to implement _deserialize_this().
        Note: this collects post-init fields as well."""
        assert is_dataclass(cls)
        if inspect.isabstract(cls):
            raise TypeError(
                "cannot instantiate abstract class",
                {"cls": cls, "serialized": serialized},
            )

        _undefined = object()

        def deserialize_field(_fd: Field):
            if _fd.name in overrides:
                return overrides[_fd.name]
            if _fd.name in serialized:
                if _fd.name not in cls._get_type_hints():
                    raise SerializationError(
                        description=f'field "{_fd.name}" should have explicit type hint or provided as "overrides"'
                    )
                return deserialize(
                    cls._get_type_hints()[_fd.name], serialized[_fd.name]
                )
            return _undefined
            # TODO: post-init fields should be explicitly set inside each _deserialize_this()
            # if _fd.default or _fd.default_factory:
            #     return undefined
            # raise SerializationError(
            #     f'field "{_fd.name}" has no default value, '
            #     f'therefore it should be provided either as "serialized" or "overrides"')

        init_params: dict[str, Any] = {}
        post_init_params: dict[str, Any] = {}
        # noinspection PyDataclass
        for fd in fields(cls):
            fd_value = deserialize_field(fd)
            if fd_value is _undefined:
                continue
            if fd.init:
                init_params[fd.name] = fd_value
            else:
                post_init_params[fd.name] = fd_value

        # noinspection PyArgumentList
        self = cls(**init_params)
        for fd_name, fd_value in post_init_params.items():
            setattr(self, fd_name, fd_value)
        return self

    @classmethod
    @cache
    def _get_type_hints(cls) -> dict[str, type]:
        return get_type_hints(cls)

    @final
    def _repr_non_default_fields(self):
        """this can only be called from a dataclass.
        helper method to implement __repr__()."""
        # noinspection PyDataclass
        assert is_dataclass(self)
        # noinspection PyDataclass
        return (
            f"{type(self).__name__}("
            + ",".join(
                f"{fd.name}={getattr(self, fd.name)}"
                for fd in fields(self)
                if getattr(self, fd.name) != fd.default
            )
            + ")"
        )


class DualSerializable(Serializable, Deserializable, metaclass=ABCMeta):
    """dataclass representation of the resources defined in Notion REST API.
    interchangeable with JSON object.
    field with `init=False` are usually the case which not required from user-side but provided from server-side."""

    pass


def serialize_datetime(dt: date | datetime):
    if isinstance(dt, datetime):
        dt = dt.replace(tzinfo=my_tz).astimezone(my_tz)
    return dt.isoformat()


def deserialize_datetime(serialized: str) -> date | datetime:
    """
    Raises:
        dateutil.parser.ParserError
    """
    try:
        dt = dateutil.parser.parse(serialized)
    except dateutil.parser.ParserError as e:
        print(serialized)
        raise e
    if re.match(r"^\d{4}-\d{2}-\d{2}$", serialized):
        return dt.date()
    return dt.astimezone(my_tz)
