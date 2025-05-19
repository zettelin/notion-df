from dataclasses import dataclass

from notion_df.core.collection import coalesce_dataclass, Paginator


def test_paginator():
    p = Paginator(int, iter(range(3)))
    assert p._values == []
    p._fetch_until(1)
    assert p._values == [0, 1]


def test_coalesce_dataclass():
    @dataclass
    class ExampleDataClass:
        field1: int | None = None
        field2: str | None = None
        field3: float | None = None

    instance1 = ExampleDataClass(field1=1, field2=None, field3=2.5)
    instance2 = ExampleDataClass(field1=None, field2="Hello", field3=None)
    coalesce_dataclass(instance1, instance2)
    assert instance1 == ExampleDataClass(field1=1, field2="Hello", field3=2.5)
