from __future__ import annotations

from notion_zap.apps.prop_matcher.processors.bind_simple_props import BindSimpleProperties
from notion_zap.apps.prop_matcher.processors.conform_format import TimeFormatConformer
from notion_zap.apps.prop_matcher.processors.get_date_by_created_time \
    import DateProcessorByCreatedTime
from notion_zap.apps.prop_matcher.processors.get_date_by_earliest_ref \
    import DateProcessorByEarliestRef
from notion_zap.apps.prop_matcher.processors.get_week_by_date_ref \
    import PeriodProcessorByDateRef
from notion_zap.apps.prop_matcher.processors.get_week_by_from_date \
    import WeekRowProcessorFromDate
from notion_zap.apps.prop_matcher.processors.match_to_itself import SelfProcessor
from notion_zap.apps.prop_matcher.struct import MainEditorDepr
from notion_zap.cli.editors import Database


class RegularMatchController:
    def __init__(self):
        self.bs = MainEditorDepr()
        self.bs.root.exclude_archived = True
        self.fetch = RegularMatchFetchManager(self.bs)
        self.process = RegularMatchProcessManager(self.bs)

    def __call__(self, request_size=0):
        self.fetch(request_size)
        self.process()


class RegularMatchProcessManager:
    def __init__(self, bs: MainEditorDepr):
        self.bs = bs
        self.processor_groups = [
            [TimeFormatConformer(self.bs)],
            [DateProcessorByEarliestRef(self.bs)],  # created time보다 우선순위가 높아야 한다
            [DateProcessorByCreatedTime(self.bs),
             WeekRowProcessorFromDate(self.bs),
             PeriodProcessorByDateRef(self.bs),
             SelfProcessor(self.bs),
             BindSimpleProperties(self.bs), ]
        ]

    def __call__(self):
        for group in self.processor_groups:
            for processor in group:
                processor()
            self.bs.save()


class RegularMatchFetchManager:
    def __init__(self, bs: MainEditorDepr):
        self.bs = bs

    def __call__(self, request_size=0):
        for table in self.bs.root.block_aliases.values():
            self.fetch_table(table, request_size)

    def fetch_table(self, table: Database, request_size):
        if table in [self.bs.channels, self.bs.projects]:
            return

        query = table.rows.open_query()
        manager = query.filter_manager_by_tags
        ft = query.open_filter()

        # OR clauses
        if table is not self.bs.readings:
            for tag in ['itself', 'periods', 'dates']:
                try:
                    ft |= manager.relation(tag).is_empty()
                except KeyError:
                    pass

        # OR clauses
        if table in [self.bs.periods, self.bs.dates]:
            ft |= manager.date('date_manual').is_empty()
        if table in [self.bs.checks, self.bs.journals]:
            # TODO : gcal_sync_status
            ft |= manager.relation('dates_created').is_empty()
        if table is self.bs.readings:
            ft |= manager.relation('itself').is_empty()

            begin = manager.relation('periods_begin').is_empty()
            begin &= manager.checkbox('no_exp').is_empty()
            ft |= begin

            begin = manager.relation('dates_begin').is_empty()
            begin &= manager.checkbox('no_exp').is_empty()
            ft |= begin

            ft |= manager.relation('dates_created').is_empty()
            ft |= manager.select('media_type').is_empty()

        # ft.preview()
        query.push_filter(ft)
        query.execute(request_size)


if __name__ == '__main__':
    RegularMatchController()(request_size=20)
