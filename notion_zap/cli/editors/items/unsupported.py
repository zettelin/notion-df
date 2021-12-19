from typing import Any

from ..structs.base_logic import Gatherer
from ..structs.block_main import Block


# noinspection PyMethodMayBeStatic
class UnsupportedBlock(Block):
    def __init__(self, caller: Gatherer, id_or_url: str):
        super().__init__(caller, id_or_url)

    @property
    def block_name(self):
        return self.block_url

    @property
    def is_supported_type(self) -> bool:
        return False

    @property
    def can_have_children(self) -> bool:
        return False

    def read_contents(self) -> dict[str, Any]:
        return {}

    def richly_read_contents(self) -> dict[str, Any]:
        return {}

    def save(self):
        return {}

    def save_info(self):
        return {}

    def save_required(self) -> bool:
        return False
