from pprint import pprint

from interface.requests.query_filter_maker import QueryFilterMaker
from interface.requests.query_filter_unit import QueryFilter, PlainFilter
from interface.requests.query_sort import QuerySort
from interface.requests.requestor import RecursiveRequestor, retry


class Query(RecursiveRequestor):
    def __init__(self, page_id: str, database_parser=None):
        self._page_id = {'database_id': page_id}
        self._filter = PlainFilter({})
        self._filter_is_not_empty = False
        self.sort = QuerySort()
        self.filter_maker = QueryFilterMaker()
        if database_parser is not None:
            self.filter_maker.add_db_retrieve(database_parser)

    def apply(self, print_result=False):
        filter_apply = {'filter': self._filter.apply()} \
            if self._filter_is_not_empty else None
        return self._merge_dict(self._page_id, self.sort.apply(), filter_apply)

    @retry
    def _execute_once(self, page_size=None, start_cursor=None):
        start_cursor = {'start_cursor': start_cursor} if start_cursor else None
        page_size = {'page_size': (page_size if page_size else self.MAX_PAGE_SIZE)}
        args = self._merge_dict(self.apply(), start_cursor, page_size)
        response = self.notion.databases.query(**args)
        return response

    def clear_filter(self):
        self._filter = PlainFilter({})
        self._filter_is_not_empty = False

    def push_filter(self, query_filter: QueryFilter):
        self._filter = query_filter
        self._filter_is_not_empty = True
