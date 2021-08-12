from __future__ import annotations
from notion_py.interface import DataFrame, PageList, TabularPage
from notion_py.gateway.parse import PageListParser
from ..constants import ID_THEMES, ID_IDEAS


class SelfRelatedDataFrame(DataFrame):
    def __init__(self, database_id: str, database_name: str,
                 prop_name: dict[str, str], unit=TabularPage):
        super().__init__(database_id, database_name, prop_name, unit)
        self.upward_keys = \
            [(key, self.get_flag(key)) for key in prop_name
             if any(flag in key for flag in self.edge_directions['up'])]
        self.downward_keys = \
            [(key, self.get_flag(key)) for key in prop_name
             if any(flag in key for flag in self.edge_directions['down'])]

    edge_directions = {
        'up': ['hi', 'out'],
        'down': ['lo', 'in'],
    }
    edge_weights = {
        'hi': 'strong',
        'lo': 'strong',
        'out': 'weak',
        'in': 'weak',
    }

    @staticmethod
    def _pagelist():
        return SelfRelatedPageList

    @staticmethod
    def get_flag(key: str):
        return key.split('_')[1]

    @classmethod
    def parse_edge_type(cls, relation_type: str):
        weight = cls.edge_weights
        return weight[relation_type.split('_')[0]]


class SelfRelatedPageList(PageList):
    def __init__(self, dataframe: SelfRelatedDataFrame,
                 parsed_query: PageListParser, unit=TabularPage):
        super().__init__(dataframe, parsed_query, unit)
        assert isinstance(self.dataframe, SelfRelatedDataFrame)

    def pages_related(self, alien_page: TabularPage,
                      alien_pagelist: SelfRelatedPageList, prop_name: str):
        res = []
        # TODO > 이 명령을 직관적으로 만드는 것이 TabularPage에 DataFrame을 이식할 때
        #  꼭 구현해야 할 점이다.
        for page_id in alien_page.props.read[
                alien_pagelist.dataframe.props[prop_name].name]:
            try:
                res.append(self.page_by_id(page_id))
            except KeyError:
                # if not res:
                #    from notion_py.utility import page_id_to_url
                #    print(alien_page.title, prop_name, page_id_to_url(page_id))
                continue
        return res


THEME_PROP_NAME = {
    'hi_themes': '✖️구성',
    'out_themes': '➕합류',
    'in_themes': '➖분기',
    'lo_themes': '➗요소',

    'hi_ideas': '📕구성',
    'in_ideas': '📕속성',
}
theme_dataframe = SelfRelatedDataFrame(ID_THEMES, 'themes', THEME_PROP_NAME)

IDEA_PROP_NAME = {
    'hi_ideas': '✖️구성',
    'out_ideas': '➕적용',
    'in_ideas': '➖속성',
    'lo_ideas': '➗요소',

    'out_themes': '📕적용',
    'lo_themes': '📕요소',
}
idea_dataframe = SelfRelatedDataFrame(ID_IDEAS, 'ideas', IDEA_PROP_NAME)
