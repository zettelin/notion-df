from abc import ABCMeta

from notion_df.resource.core import Resource


class PropertySchema(Resource, metaclass=ABCMeta):
    ...
