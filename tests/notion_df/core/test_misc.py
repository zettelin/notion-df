import uuid

import pytest

from notion_df.core.uuid_parser import get_page_or_database_id

block_uuid = uuid.uuid4()
block_uuid_dash = str(block_uuid)
block_uuid_no_dash = block_uuid_dash.replace("-", "")
view_uuid_no_dash = str(uuid.uuid4()).replace("-", "")


@pytest.mark.parametrize(
    "test_input",
    [
        f"https://www.notion.so/workspace-name/{block_uuid_dash}?v={view_uuid_no_dash}&pvs=4",
        f"https://www.notion.so/workspace-name/{block_uuid_no_dash}?v={view_uuid_no_dash}&pvs=4",
        f"https://www.notion.so/workspace-name/page-name-{block_uuid_dash}?pvs=4",
        f"https://www.notion.so/workspace-name/page-name-{block_uuid_dash}?pvs=4",
        f"www.notion.so/workspace-name/{block_uuid_dash}?v=ffc764042a4244119190932603fcb416&pvs=4",
        f"www.notion.so/workspace-name/{block_uuid_no_dash}?v=ffc764042a4244119190932603fcb416&pvs=4",
        f"{block_uuid_dash}?v=ffc764042a4244119190932603fcb416&pvs=4",
        f"{block_uuid_no_dash}?v=ffc764042a4244119190932603fcb416&pvs=4",
        block_uuid_dash,
        block_uuid_no_dash,
    ],
)
def test_get_id(test_input):
    assert get_page_or_database_id(test_input) == block_uuid
