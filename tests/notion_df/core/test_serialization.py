from datetime import datetime, date

from notion_df.core.serialization import deserialize_datetime, serialize_datetime
from notion_df.core.variable import my_tz


def test_serde_datetime():
    assert serialize_datetime(date(2023, 1, 1)) == "2023-01-01"
    assert serialize_datetime(datetime(2023, 1, 1)) == "2023-01-01T00:00:00+09:00"
    assert deserialize_datetime("2023-01-01") == date(2023, 1, 1)
    assert deserialize_datetime("2023-01-01T00:00:00+09:00") == datetime(
        2023, 1, 1, tzinfo=my_tz
    )
