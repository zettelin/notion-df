from abc import ABCMeta
import datetime as dt

from notion_zap.cli import editors
from notion_zap.cli.struct import DateFormat
from ..common.struct import Matcher
from ..common.date_handler import DateHandler
from ..common.helpers import (
    fetch_unique_page_from_relation,
    query_unique_page_by_idx
)


class PeriodMatcherAbs(Matcher, metaclass=ABCMeta):
    tag__doms_tar = tag__refs_tar = 'to_periods'
    tag__tars_idx = 'title'
    tag__tars_date = 'manual_date_range'

    def __init__(self, bs):
        super().__init__(bs)
        self.target = self.bs.periods
        self.target_by_idx = self.target.by_idx_value_at(self.tag__tars_idx)

    def find_or_create_by_date_val(self, date_val: dt.date):
        if tar := self.find_by_date_val(date_val):
            return tar
        return self.create_by_date_val(date_val)

    def find_by_date_val(self, date_val: dt.date):
        if not date_val:
            return None
        date_handler = DateHandler(date_val)
        tar_idx = date_handler.strf_year_and_week()
        if tar := self.target_by_idx.get(tar_idx):
            return tar
        if tar := query_unique_page_by_idx(self.target, tar_idx, self.tag__tars_idx,
                                           'title'):
            self.target_by_idx.update({tar_idx: tar})
            return tar
        return None

    def create_by_date_val(self, date_val: dt.date):
        if not date_val:
            return None
        tar = self.target.create_page()
        date_handler = DateHandler(date_val)

        tar_idx_val = date_handler.strf_year_and_week()
        tar.props.write_title_at(self.tag__tars_idx, tar_idx_val)
        self.target_by_idx.update({tar_idx_val: tar})

        date_range = DateFormat(start=date_handler.first_day_of_week(),
                                end=date_handler.last_day_of_week())
        tar.props.write_date_at(self.tag__tars_date, date_range)
        return tar.save()

    def update_tar(self, tar: editors.PageRow, tar_idx_val=None,
                   disable_overwrite=False):
        """provide tar_idx_val manually if yet not synced to server-side"""
        if tar_idx_val is None:
            tar_idx_val = tar.props.read_at(self.tag__tars_idx)
        date_handler = DateHandler.from_strf_year_and_week(tar_idx_val)

        date_range = DateFormat(start=date_handler.first_day_of_week(),
                                end=date_handler.last_day_of_week())
        if date_range != tar.props.read_at(self.tag__tars_date):
            self.bs.root.disable_overwrite = disable_overwrite
            tar.props.write_date_at(self.tag__tars_date, date_range)
            self.bs.root.disable_overwrite = False


class PeriodTargetAutoFiller(PeriodMatcherAbs):
    def __init__(self, bs, disable_overwrite, create_date_range):
        super().__init__(bs)
        self.disable_overwrite = disable_overwrite
        from ..build_calendar import CalendarDateRange
        self.create_date_range: CalendarDateRange = create_date_range

    def execute(self):
        for tar in self.target:
            self.update_tar(tar, disable_overwrite=self.disable_overwrite)
        if self.create_date_range:
            for date_val in self.create_date_range.iter_date():
                if self.find_by_date_val(date_val):
                    continue
                self.create_by_date_val(date_val)


class PeriodMatcherType1(PeriodMatcherAbs):
    doms_date = 'manual_date'

    def __init__(self, bs):
        super().__init__(bs)
        self.domains = [self.bs.dates]

    def execute(self):
        for domain in self.domains:
            for dom in domain:
                if tar := self.determine_tar(dom):
                    dom.props.write_relation_at(self.tag__doms_tar, tar.block_id)

    def determine_tar(self, dom: editors.PageRow):
        if dom.props.read_at(self.tag__doms_tar):
            return None
        dom_idx: DateFormat = dom.props.read_at(self.doms_date)
        date_val = dom_idx.start_date
        return self.find_or_create_by_date_val(date_val)


class PeriodMatcherType2(PeriodMatcherAbs):
    doms_ref = 'to_dates'

    def __init__(self, bs):
        super().__init__(bs)
        self.reference = self.bs.dates
        self.domains = [
            self.bs.journals, self.bs.writings, self.bs.memos, self.bs.schedules,
            self.bs.readings
        ]

    def execute(self):
        for domain in self.domains:
            for dom in domain:
                if tar := self.determine_tar(dom):
                    dom.props.write_relation_at(self.tag__doms_tar, tar.block_id)

    def determine_tar(self, dom: editors.PageRow):
        if dom.props.read_at(self.tag__doms_tar):
            return None
        if ref := fetch_unique_page_from_relation(dom, self.reference, self.doms_ref):
            if tar := fetch_unique_page_from_relation(
                    ref, self.target, self.tag__refs_tar):
                return tar
        return None


class PeriodMatcherType3(PeriodMatcherAbs):
    tag__doms_tar = 'to_scheduled_periods'
    tag__doms_ref = 'to_scheduled_dates'
    tag__refs_tar = 'to_periods'

    def __init__(self, bs):
        super().__init__(bs)
        self.reference = self.bs.dates
        self.domains = [self.bs.schedules]

    def execute(self):
        for domain in self.domains:
            for dom in domain:
                if tar := self.determine_tar(dom):
                    dom.props.write_relation_at(self.tag__doms_tar, tar.block_id)

    def determine_tar(self, dom: editors.PageRow):
        if dom.props.read_at(self.tag__doms_tar):
            return None
        if ref := fetch_unique_page_from_relation(
                dom, self.reference, self.tag__doms_ref):
            if tar := fetch_unique_page_from_relation(
                    ref, self.target, self.tag__refs_tar):
                return tar
        return None
