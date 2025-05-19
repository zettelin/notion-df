from inspect import isabstract

import pytest

from notion_df2.object.misc import Icon, File, Emoji, InternalFile, ExternalFile
from notion_df2.core.serializable import registry__get_dispatch_class, Deserializable


@pytest.mark.parametrize("cls", [Icon, File, Emoji, InternalFile, ExternalFile])
def test_deserializable_classes(cls: type[Deserializable]):
    if isabstract(cls):
        assert cls in registry__get_dispatch_class
