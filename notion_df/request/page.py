from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from notion_df.core.request import SingleRequestBuilder, RequestSettings, Version, Method, PaginatedRequestBuilder, \
    RequestBuilder
from notion_df.data.common import Icon
from notion_df.data.entity_data import BlockValue, serialize_block_value_list, PageData
from notion_df.data.file import ExternalFile
from notion_df.data.partial_parent import PartialParent
from notion_df.property import PageProperties, Property, property_registry, PagePropertyValue_T
from notion_df.util.collection import DictFilter


@dataclass
class RetrievePage(SingleRequestBuilder[PageData]):
    """https://developers.notion.com/reference/retrieve-a-page"""
    id: UUID
    response_type = PageData

    def get_settings(self) -> RequestSettings:
        return RequestSettings(Version.v20220628, Method.GET,
                               f'https://api.notion.com/v1/pages/{self.id}')

    def get_body(self) -> None:
        return


@dataclass
class CreatePage(SingleRequestBuilder[PageData]):
    """https://developers.notion.com/reference/post-page"""
    response_type = PageData
    parent: PartialParent
    properties: PageProperties = field(default_factory=PageProperties)
    children: list[BlockValue] = None
    icon: Optional[Icon] = field(default=None)
    cover: Optional[ExternalFile] = field(default=None)

    def get_settings(self) -> RequestSettings:
        return RequestSettings(Version.v20220628, Method.POST,
                               f'https://api.notion.com/v1/pages')

    def get_body(self) -> dict[str, Any]:
        return DictFilter.not_none({
            "parent": self.parent,
            "icon": self.icon,
            "cover": self.cover,
            "properties": self.properties,
            "children": serialize_block_value_list(self.children),
        })


@dataclass
class UpdatePage(SingleRequestBuilder[PageData]):
    """https://developers.notion.com/reference/patch-page"""
    # TODO: inspect that UpdatePage.response immediately update the page.last_response status ? (b031c3a)
    response_type = PageData
    id: UUID
    properties: Optional[PageProperties] = None
    """send empty PageProperty to delete all properties."""
    icon: Optional[Icon] = field(default=None)
    cover: Optional[ExternalFile] = field(default=None)
    archived: Optional[bool] = None

    def get_settings(self) -> RequestSettings:
        return RequestSettings(Version.v20220628, Method.PATCH,
                               f'https://api.notion.com/v1/pages/{self.id}')

    def get_body(self) -> dict[str, Any]:
        return DictFilter.not_none({
            "icon": self.icon,
            "cover": self.cover,
            "properties": self.properties,
            "archived": self.archived,
        })


@dataclass
class RetrievePagePropertyItem(RequestBuilder):
    """https://developers.notion.com/reference/retrieve-a-page-property"""
    # for simplicity reasons, pagination is not supported.
    page_id: UUID
    property_id: str

    def get_settings(self) -> RequestSettings:
        return RequestSettings(Version.v20220628, Method.GET,
                               f'https://api.notion.com/v1/pages/{self.page_id}/properties/{self.property_id}')

    def get_body(self) -> None:
        return

    execute_once = PaginatedRequestBuilder.execute_once

    def execute(self) -> tuple[Property[Any, PagePropertyValue_T, Any], PagePropertyValue_T]:
        data = self.execute_once()
        if (prop_serialized := data)['object'] == 'property_item':
            # noinspection PyProtectedMember
            return Property._deserialize_page_value(prop_serialized)

        data_list = [data]
        while data['has_more']:
            start_cursor = data['next_cursor']
            data = self.execute_once(start_cursor=start_cursor)
            data_list.append(data)

        typename = data_list[0]['property_item']['type']
        value_list = []
        for data in data_list:
            for result in data['results']:
                value_list.append(result[typename])
        prop_serialized = {'type': typename, typename: value_list, 'has_more': False}

        # TODO deduplicate with PageProperties._deserialize_this()
        property_key_cls = property_registry[typename]
        property_key = property_key_cls(None)
        property_key.id = self.property_id
        # noinspection PyProtectedMember
        property_value = property_key_cls._deserialize_page_value(prop_serialized)
        return property_key, property_value
