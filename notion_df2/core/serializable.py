from abc import ABCMeta, abstractmethod
from inspect import isabstract
from typing import Any, Callable, Iterable, Self, TypeVar, final

from loguru import logger


class Serializable(metaclass=ABCMeta):
    """Representation of the resources defined in Notion REST API.
    Can be dumped into JSON object."""

    @abstractmethod
    def serialize(self) -> Any:
        """
        Returns:
            python object (not JSON string)
        Raises:
            SerializationError
        """


class Deserializable(metaclass=ABCMeta):
    """Representation of the resources defined in Notion REST API.
    Can be loaded from JSON object."""

    @classmethod
    @final
    def deserialize(cls, data: Any) -> Self:
        """
        Parameters:
            data: python object (not JSON string)
        Raises:
            DeserializationError
        """
        if isabstract(cls):
            try:
                get_dispatch_class = registry__get_dispatch_class[cls]
            except KeyError:
                raise NotImplementedError(
                    f"Dispatcher not added for the base class. Cannot find a concrete class."
                    f" cls={cls.__name__}"
                )
            dispatch_class = get_dispatch_class(data)
            return dispatch_class.deserialize(data)
        else:
            return cls._deserialize(data)

    @classmethod
    @abstractmethod
    def _deserialize(cls, data: Any) -> Self:
        """
        Parameters:
            data: python object (not JSON string)
        Raises:
            DeserializationError
        """
        raise NotImplementedError


registry__get_dispatch_class: dict[type[Deserializable], Callable[[Any], type[Deserializable]]] = {}


class DualSerializable(Serializable, Deserializable, metaclass=ABCMeta):
    """Dataclass representation of the resources defined in Notion REST API.
    Interchangeable with JSON object."""


TypeDT = TypeVar("TypeDT", bound=type[Deserializable])


class Dispatcher[TypeDT](metaclass=ABCMeta):
    def __init__(self, client_class: TypeDT, parent_dispatchers: Iterable[Self] = ()) -> None:
        self.client_class = client_class
        self.other_dispatchers = parent_dispatchers
        registry__get_dispatch_class[client_class] = self.get_dispatch_class

    def __repr__(self) -> str:
        if not self.other_dispatchers:
            return f"{type(self).__name__}({self.client_class.__name__})"
        else:
            return (f"{type(self).__name__}({self.client_class.__name__},"
                    f" [{", ".join(dispatcher.client_class.__name__ for dispatcher in self.other_dispatchers)}])")

    @abstractmethod
    def get_dispatch_class(self, data: dict) -> TypeDT: ...


class TypeBasedDispatcher(Dispatcher[TypeDT]):
    """Dispatch by the value of data["type"], or, typename."""
    _registry: dict[str, type[Deserializable]] = {}

    def register(self, typename: str) -> Callable[[TypeDT], TypeDT]:
        def wrapper(cls: TypeDT) -> TypeDT:
            self._registry[typename] = cls
            return cls

        return wrapper

    def get_dispatch_class(self, data: dict) -> TypeDT:
        typename = data.get("type")
        try:
            ret = self._registry[typename]
            logger.debug(f"{self}.get_dispatch_class() => {ret}")
            return ret
        except KeyError:
            raise KeyError(f"{self}.get_dispatch_class({typename=}, registry={set(self._registry.keys())})")
