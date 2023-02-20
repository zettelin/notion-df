from __future__ import annotations

import inspect
import types
import typing
from abc import abstractmethod, ABCMeta
from dataclasses import dataclass, fields, InitVar
from datetime import datetime
from enum import Enum
from typing import Any, final, ClassVar, Optional, cast, TypeVar

import dateutil.parser
from typing_extensions import Self

from notion_df.util.collection import KeyChain, FinalDict
from notion_df.util.misc import NotionDfValueError
from notion_df.variables import Variables


def serialize(obj: Any):
    """unified serializer for both Serializable and external classes."""
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list) or isinstance(obj, set):
        return [serialize(e) for e in obj]
    if isinstance(obj, Serializable):
        return obj.serialize()
    for typ in {bool, str, int, float}:
        if isinstance(obj, typ):
            return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return DateTimeSerializer.serialize(obj)
    raise NotionDfValueError('cannot serialize', {'obj': obj})


def deserialize(serialized: Any, typ: type):
    """unified deserializer for both Deserializable and external classes."""
    err_vars = {'typ': typ, 'serialized': serialized}
    if isinstance(typ, types.GenericAlias):
        origin: type = typing.get_origin(typ)
        args = typing.get_args(typ)
        err_vars.update({'typ.origin': origin, 'typ.args': args})
        try:
            if issubclass(origin, dict):
                value_type = args[1]
                return {k: deserialize(v, value_type) for k, v in serialized.items()}
            element_type = args[0]
            if issubclass(origin, list):
                return [deserialize(e, element_type) for e in serialized]
            if issubclass(origin, set):
                return {deserialize(e, element_type) for e in serialized}
            raise NotionDfValueError('cannot deserialize: GenericAlias type with invalid origin', err_vars)
        except IndexError:
            raise NotionDfValueError('cannot deserialize: GenericAlias type with invalid args', err_vars)
    # TODO: resolve (StrEnum | str) to str - or, is that really needed?
    # if isinstance(typ, types.UnionType):
    #    err_description = 'UnionType is (currently) not supported'
    if not inspect.isclass(typ):
        raise NotionDfValueError('cannot deserialize: not supported type', err_vars)
    if issubclass(typ, Deserializable):
        return typ.deserialize(serialized)
    if typ in {bool, str, int, float}:
        if type(serialized) != typ:
            raise NotionDfValueError('cannot deserialize: type(serialized) != typ', err_vars)
        return serialized
    if issubclass(typ, Enum):
        return typ(serialized)
    if issubclass(typ, datetime):
        return DateTimeSerializer.deserialize(serialized)
    if isinstance(typ, InitVar):  # TODO: is this really needed?
        return deserialize(serialized, typ.type)
    raise NotionDfValueError('cannot deserialize: not supported class', err_vars)


class DateTimeSerializer:
    @staticmethod
    def get_timezone():
        return Variables.timezone

    @classmethod
    def serialize(cls, dt: datetime):
        return dt.astimezone(cls.get_timezone()).isoformat()  # TODO: check Notion time format

    @classmethod
    def deserialize(cls, dt_string: str):
        datetime_obj = dateutil.parser.parse(dt_string)
        return datetime_obj.astimezone(cls.get_timezone())


@dataclass
class Serializable(metaclass=ABCMeta):
    """dataclass representation of the resources defined in Notion REST API.
    transformable into JSON object."""

    def __init__(self, **kwargs):
        pass

    @final
    def __init_subclass__(cls, **kwargs):
        """this method is reserved. use cls._init_subclass() instead"""
        super().__init_subclass__(**kwargs)
        if cls._skip_init_subclass():
            return
        cls._init_subclass(**kwargs)

    @classmethod
    def _init_subclass(cls, **kwargs):
        dataclass(cls)

    @classmethod
    def _skip_init_subclass(cls) -> bool:
        return inspect.isabstract(cls) or cls.__name__.startswith('_')

    @final
    def serialize(self) -> dict[str, Any]:
        field_value_dict = {fd.name: getattr(self, fd.name) for fd in fields(self)}
        data_obj_with_each_field_serialized = type(self)(
            **{fd_name: serialize(fd_value) for fd_name, fd_value in field_value_dict.items()})
        return data_obj_with_each_field_serialized._plain_serialize()

    @abstractmethod
    def _plain_serialize(self) -> dict[str, Any]:
        """serialize only the first depth structure, leaving each field value not serialized."""
        pass


_Deserializable_T = TypeVar('_Deserializable_T', bound='Deserializable')


class _DeserializableRegistry:
    def __init__(self):
        self.data: dict[type[Deserializable], FinalDict[KeyChain, type[Deserializable]]] = {}
        """schema: '{master: {keychain: {subclasses} } }'"""

    def set_master(self, master: type[_Deserializable_T]) -> type[_Deserializable_T]:
        """set an abstract base deserializable class as a representative resource,
        allowing it to distinguish its several subclasses' serialized form.
        use as a decorator."""
        assert issubclass(master, Deserializable)
        if not inspect.isabstract(master):
            raise NotionDfValueError('master class must be abstract', {'cls': master})
        self.data[master] = FinalDict()
        return master

    def set_subclass(self, subclass: type[Deserializable], subclass_mock_serialized: dict[str, Any]) -> None:
        master: Optional[type[Deserializable]] = None
        for base in subclass.__mro__:
            if base in self.data:  # if base is master
                master = cast(type[Deserializable], base)  # type: ignore
                break
        if master is None:
            return
        subclass_type_keychain = self.find_type_keychain(subclass_mock_serialized)
        self.data[master][subclass_type_keychain] = subclass

    def find_subclass(self, master: type[Deserializable], serialized: dict[str, Any]) -> type[Deserializable]:
        type_keychain = self.find_type_keychain(serialized)
        if master not in self.data:
            raise NotionDfValueError('cannot proxy-deserialize from non-master abstract class', {'cls': master})
        if type_keychain not in self.data[master]:
            raise NotionDfValueError('cannot proxy-deserialize: unexpected type keychain',
                                     {'cls': master, 'type_keychain': type_keychain})
        subclass = self.data[master][type_keychain]
        return subclass

    @staticmethod
    def find_type_keychain(serialized: dict[str, Any]) -> KeyChain:
        current_keychain = KeyChain()
        if 'type' not in serialized:
            raise NotionDfValueError(
                "cannot deserialize via master: 'type' key not found in serialized data",
                {'serialized.keys()': list(serialized.keys()), 'serialized': serialized},
                linebreak=True
            )
        while True:
            key = serialized['type']
            current_keychain += key,
            if (value := serialized.get(key)) and isinstance(value, dict) and 'type' in value:
                serialized = value
                continue
            return current_keychain


_deserializable_registry = _DeserializableRegistry()
set_master = _deserializable_registry.set_master


@dataclass
class Deserializable(Serializable, metaclass=ABCMeta):
    """dataclass representation of the resources defined in Notion REST API.
    interchangeable to JSON object.
    decorate with '@set_master' to use as a unified deserializer entrypoint."""
    __registry: ClassVar[_DeserializableRegistry] = _deserializable_registry
    """data structure to handle master-subclasses relation of deserializable."""
    _field_type_dict: ClassVar[dict[str, type]]
    """helper attribute used to generate deserialize() from parsing _plain_serialize()."""
    _field_keychain_dict: ClassVar[dict[KeyChain, str]]
    """helper attribute used to generate _plain_deserialize() from parsing _plain_serialize()."""

    @dataclass(frozen=True)
    class _MockAttribute:
        name: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @classmethod
    def _init_subclass(cls, **kwargs) -> None:
        super()._init_subclass(**kwargs)
        cls._field_type_dict = {field.name: field.type for field in fields(cls)}
        mock_serialized = cls._get_mock_serialized()
        cls.__registry.set_subclass(cls, mock_serialized)
        if inspect.getsource(cls.deserialize) != inspect.getsource(Deserializable.deserialize):
            # if deserialize() is overridden, in other words, manually configured,
            #  it need not be generated from deserialize()
            return
        cls._field_keychain_dict = cls._get_field_keychain_dict(mock_serialized)

    @classmethod
    def _get_mock_serialized(cls) -> dict[str, Any]:
        @dataclass
        class MockResource(cls, metaclass=ABCMeta):
            @classmethod
            def _skip_init_subclass(cls):
                return True

        MockResource.__name__ = cls.__name__
        init_param_keys = list(inspect.signature(MockResource.__init__).parameters.keys())[1:]
        mock_init_param = {k: cls._MockAttribute(k) for k in init_param_keys}
        _mock = MockResource(**mock_init_param)  # type: ignore
        for field in fields(MockResource):
            setattr(_mock, field.name, cls._MockAttribute(field.name))
        return _mock._plain_serialize()

    @classmethod
    def _get_field_keychain_dict(cls, mock_serialized: dict[str, Any]) -> dict[KeyChain, str]:
        field_keychain_dict = FinalDict[KeyChain, str]()
        items: list[tuple[KeyChain, Any]] = [(KeyChain((k,)), v) for k, v in mock_serialized.items()]
        while items:
            keychain, value = items.pop()
            if isinstance(value, cls._MockAttribute):
                attr_name = value.name
                field_keychain_dict[keychain] = attr_name
            elif isinstance(value, dict):
                items.extend((keychain + (k,), v) for k, v in value.items())
        return field_keychain_dict

    @classmethod
    def deserialize(cls, serialized: dict[str, Any]) -> Self:
        if inspect.isabstract(cls):
            return cls.__registry.find_subclass(cls, serialized).deserialize(serialized)
        each_field_serialized_dict = {}
        for keychain, field_name in cls._field_keychain_dict.items():
            each_field_serialized_dict[field_name] = keychain.get(serialized)
        field_value_dict = {}
        for field_name, field_serialized in each_field_serialized_dict.items():
            field_value_dict[field_name] = deserialize(field_serialized, cls._field_type_dict[field_name])
        return cls(**field_value_dict)  # nomypy
