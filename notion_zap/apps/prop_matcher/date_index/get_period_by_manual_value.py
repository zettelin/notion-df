from __future__ import annotations

import datetime as dt

from notion_zap.cli.editors import PageRow, Database
from notion_zap.cli.structs import DateObject
from notion_zap.apps.prop_matcher.common import has_value, set_value, query_unique_page_by_idx
from notion_zap.apps.prop_matcher.date_index.date_formatter import DateHandler
from notion_zap.apps.prop_matcher.struct import EditorBase, MainEditor


class PeriodMatcherByManualValue(MainEditor):
    def __init__(self, bs: EditorBase):
        super().__init__(bs)
        self.tag_period = 'periods'
        self.get_period = PeriodGetterFromDateValue(self.bs.periods)

    def __call__(self):
        for table, tag_manual_value in [(self.bs.dates, 'dateval_manual')]:
            for row in table.rows:
                if has_value(row, self.tag_period):
                    continue
                date_val = get_date_val(row, tag_manual_value)
                if period := self.get_period(date_val):
                    set_value(row, period, self.tag_period)


def get_date_val(row: PageRow, tag_manual_value):
    date_object: DateObject = row.read_tag(tag_manual_value)
    return date_object.start_date


class PeriodGetterFromDateValue:
    def __init__(self, periods: Database):
        self.periods = periods
        self.periods_by_title = self.periods.rows.index_by_tag('title')

    def __call__(self, date_val: dt.date):
        if tar := self.find_by_date_val(date_val):
            return tar
        return self.create_by_date_val(date_val)

    def find_by_date_val(self, date_val: dt.date):
        if not date_val:
            return None
        date_handler = DateHandler(date_val)
        tar_idx = date_handler.strf_year_and_week()
        if tar := self.periods_by_title.get(tar_idx):
            return tar
        if tar := query_unique_page_by_idx(self.periods, tar_idx, 'title', 'title'):
            return tar
        return None

    def create_by_date_val(self, date_val: dt.date):
        if not date_val:
            return None
        tar = self.periods.rows.open_new_page()
        date_handler = DateHandler(date_val)

        tar_idx = date_handler.strf_year_and_week()
        tar.write_title(tag='title', value=tar_idx)

        date_range = DateObject(start=date_handler.first_day_of_week(),
                                end=date_handler.last_day_of_week())
        tar.write_date(tag='manual_date_range', value=date_range)
        return tar.save()
