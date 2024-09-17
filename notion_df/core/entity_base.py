from __future__ import annotations

from abc import abstractmethod, ABCMeta
from inspect import isabstract
from typing import (Final, Generic, Hashable, Union, Optional, final, TypeVar, Any,
                    Callable, ClassVar, MutableMapping)
from uuid import UUID

from loguru import logger
from typing_extensions import Self

from notion_df.core.collection import coalesce_dataclass
from notion_df.core.data_base import EntityDataT, EntityData
from notion_df.core.definition import undefined, repr_object, Undefined
from notion_df.core.exception import ImplementationError

latest_data_dict: Final[MutableMapping[tuple[type[Entity], UUID], EntityData]] = {}
mock_data_dict: Final[MutableMapping[tuple[type[Entity], UUID], EntityData]] = {}


class Entity(Hashable, Generic[EntityDataT], metaclass=ABCMeta):
    """The base class for blocks, users, and comments.

    There is only one instance with given subclass and id.
    You can identify two blocks directly `block_1 == block_2`,
    not need to `block_1.id == block_2.id`
    """
    id: UUID
    # noinspection PyClassVar
    data_cls: ClassVar[type[EntityDataT]]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not isabstract(cls):
            assert cls.data_cls

    @staticmethod
    @abstractmethod
    def _get_id(id_or_url: Union[UUID, str]) -> UUID:
        pass

    def __init__(self, id_or_url: UUID | str):
        self.id: Final[UUID] = self._get_id(id_or_url)

    def __getnewargs__(self):  # required for pickling
        return self.id,

    @property
    def _pk(self) -> tuple[type[EntityDataT], UUID]:
        return self.data_cls, self.id

    def __hash__(self) -> int:
        return hash(self._pk)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Entity) and self._pk == other._pk

    def __repr__(self) -> str:
        return repr_object(self, id=self.id)

    @property
    def data(self) -> Union[EntityDataT, Undefined]:
        """
        Return the latest data of the entity.
        
        if the data is retrievable, this will trigger on-demand retrieval and thus never be None.
        """
        return self.local_data

    @property
    def local_data(self) -> Union[EntityDataT, Undefined]:
        return latest_data_dict.get(self._pk, mock_data_dict.get(self._pk, undefined))

    @property
    def _latest_data(self) -> Optional[EntityDataT]:
        return latest_data_dict.get(self._pk)

    @property
    def _mock_data(self) -> Optional[EntityDataT]:
        return mock_data_dict.get(self._pk)

    @abstractmethod
    def set_mock_data(self, **kwargs: Any) -> EntityDataT:
        """
        To save API calls, Set some invariant values(such as the root pages of your workspace) as mock data.
        Mock data is always at the last priority of reading data and not garbage collected.
        """
        pass


def retrieve_on_demand(func: CallableT) -> CallableT:
    def wrapper(self: RetrievableEntity, *args, **kwargs):
        if (result := func(self, *args, **kwargs)) is not undefined:
            return result
        logger.debug(f"retrieve on-demand, {self=}")
        self.retrieve()
        if (result := func(self, *args, **kwargs)) is not undefined:
            return result
        raise ImplementationError(f"{type(self)}.retrieve() did not update latest data")

    return wrapper


class RetrievableEntity(Entity[EntityDataT], Generic[EntityDataT]):
    @abstractmethod
    def retrieve(self) -> Self:
        # TODO: raise EntityNotExistError(ValueError), with page_exists()
        pass

    @final
    @property
    @retrieve_on_demand
    def data(self) -> EntityDataT:
        return self.local_data

    @final
    @property
    def local_data(self) -> Union[EntityDataT, Undefined]:
        return super().local_data

    def set_latest_data(self, data: EntityDataT) -> EntityDataT:
        past_latest_data = latest_data_dict.get(self._pk)
        if past_latest_data is None or data.timestamp >= past_latest_data.timestamp:
            latest_data_dict[self._pk] = data
            return data
        else:
            return past_latest_data

    def _set_mock_data(self, data: EntityDataT) -> EntityDataT:
        if past_mock_data := mock_data_dict.get(self._pk):
            coalesce_dataclass(data, past_mock_data)
        mock_data_dict[self._pk] = data
        return data


CallableT = TypeVar("CallableT", bound=Callable[[RetrievableEntity, ...], Any])


class CanBeParent(metaclass=ABCMeta):
    @abstractmethod
    def _repr_as_parent(self) -> str:
        pass


class HasParent(Entity, CanBeParent, metaclass=ABCMeta):
    @property
    @abstractmethod
    def parent(self) -> CanBeParent:
        pass

    @final
    def _repr_parent(self) -> str:
        if not self.local_data:
            return undefined
        return self.parent._repr_as_parent()

    def __repr__(self) -> str:
        return repr_object(self, id=self.id, parent=self._repr_parent())
