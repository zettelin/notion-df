from __future__ import annotations

import datetime as dt
import re
from abc import ABCMeta
from typing import Iterable, Optional, Any, cast

from loguru import logger

from app.action.__core__ import SequentialAction, Action
from app.emoji_code import EmojiCode
from app.my_block import (
    DatabaseEnum,
    record_timestr_prop,
    weeki_date_range_prop,
    datei_to_weeki_prop,
    record_to_datei_prop,
    record_to_tide_prop,
    record_to_read_prop,
    reading_to_date_prop,
    reading_to_start_date_prop,
    reading_to_event_prop,
    reading_match_date_by_created_time_prop,
    korean_weekday,
    record_kind_prop,
    datei_date_prop,
    work_needs_sch_datei_prop,
    parse_yymmdd,
    record_to_intent_prop,
    record_to_tap_prop,
    record_to_stage_prop,
    record_to_extent_prop,
    record_to_journal_prop,
    relevant,
    lower,
    record_contents_merged_prop,
    record_to_sch_datei_prop,
    Datei,
)
from notion_df.core.collection import Paginator
from notion_df.core.misc import repr_object
from notion_df.entity import Page, Database
from notion_df.filter import created_time_filter
from notion_df.property import (
    RelationProperty,
    TitleProperty,
    PageProperties,
    CheckboxProperty,
    CheckboxFormulaProperty,
)
from notion_df.rich_text import TextSpan, RichText


# TODO
#  - 읽기 - 📕유형 <- 꼭지> 추가 (스펙 논의 필요)
#  - 일간/주간 1년 앞서 자동생성


class MatchActionBase:
    def __init__(self):
        self.date_namespace = DateINamespace()
        self.week_namespace = WeekINamespace()


class MatchAction(Action, metaclass=ABCMeta):
    def __init__(self, base: MatchActionBase):
        self.base = base
        self.date_namespace = base.date_namespace
        self.week_namespace = base.week_namespace


class MatchSequentialAction(MatchAction, SequentialAction, metaclass=ABCMeta):
    pass


last_edited_time_checkbox = CheckboxProperty("🟣오늘")


class MatchRecordDateiByLastEditedTime(MatchSequentialAction):
    def __init__(
        self, base: MatchActionBase, record: DatabaseEnum, record_to_datei: str
    ):
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{record_to_datei}"
        )

    def query(self) -> Iterable[Page]:
        return self.record_db.query(last_edited_time_checkbox.filter.is_not_empty())

    def process_page(self, record: Page) -> None:
        if record.parent != self.record_db:
            return
        if not record.properties[last_edited_time_checkbox]:
            return
        datei = self.date_namespace.get_page_by_date(record.last_edited_time)
        properties = PageProperties(
            {
                last_edited_time_checkbox: False,
                self.record_to_datei: record.properties[self.record_to_datei] + [datei],
            }
        )
        logger.info(f"{record} -> {properties}")
        record.update(properties=properties)


class MatchRecordDateiByCreatedTime(MatchSequentialAction):
    def __init__(
        self,
        base: MatchActionBase,
        record: DatabaseEnum,
        record_to_datei: str,
        only_if_empty: bool = False,
        only_if_this_checkbox_filled: Optional[
            CheckboxProperty | CheckboxFormulaProperty
        ] = None,
    ):
        """
        :arg only_if_empty: will only add the datei if the current record[datei] is empty.
        """
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{record_to_datei}"
        )
        self.only_if_empty = only_if_empty
        self.only_if_this_checkbox_filled = only_if_this_checkbox_filled

    def __repr__(self) -> str:
        return repr_object(
            self,
            record_db_title=self.record_db.title,
            record_to_datei=self.record_to_datei,
            only_if_empty=self.only_if_empty,
        )

    def query(self) -> Paginator[Page]:
        return self.record_db.query(
            filter=(
                self.record_to_datei.filter.is_empty() if self.only_if_empty else None
            )
        )

    def process_page(self, record: Page) -> None:
        if record.parent != self.record_db:
            return
        if self.only_if_empty and record.properties[self.record_to_datei]:
            logger.info(f"{record} -> Already filled")
            return
        if (
            self.only_if_this_checkbox_filled
            and not record.properties[self.only_if_this_checkbox_filled]
        ):
            logger.info(
                f"{record} -> Checkbox not filled '{self.only_if_this_checkbox_filled}'"
            )
            return
        record_created_date = get_record_created_date(record)
        datei = self.date_namespace.get_page_by_date(record_created_date)
        if datei in (current_datei_list := record.properties[self.record_to_datei]):
            logger.info(f"{record} -> Already includes created date {datei=}")
            return
        properties = PageProperties(
            {
                self.record_to_datei: current_datei_list + [datei],
            }
        )
        if self.only_if_empty and record.retrieve().properties[self.record_to_datei]:
            logger.info(f"{record} -> Already filled in the meantime")
            return
        logger.info(f"{record} -> {properties}")
        record.update(properties)


class MatchRecordDateiByTitle(MatchSequentialAction):
    def __init__(
        self,
        base: MatchActionBase,
        record: DatabaseEnum,
        record_to_datei: str,
        only_if_empty: bool = False,
    ):
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{record_to_datei}"
        )
        self.only_if_empty = only_if_empty

    def __repr__(self) -> str:
        return repr_object(
            self,
            record_db_title=self.record_db.title,
            record_to_datei=self.record_to_datei,
        )

    def query(self) -> Paginator[Page]:
        return self.record_db.query()

    def process_page(self, record: Page) -> Any:
        if record.parent != self.record_db:
            return
        if self.only_if_empty and record.properties[self.record_to_datei]:
            logger.info(f"{record} -> Already filled")
            return
        if not (
            datei := self.date_namespace.get_page_by_record_title(
                record.properties.title.plain_text
            )
        ):
            return
        if datei in (current_datei_list := record.properties[self.record_to_datei]):
            return
        properties = PageProperties(
            {
                self.record_to_datei: current_datei_list + [datei],
            }
        )
        logger.info(f"{record} -> {properties}")
        record.update(properties)


class PrependDateiOnRecordTitle(MatchSequentialAction):
    record_to_datei: RelationProperty

    def __init__(
        self, base: MatchActionBase, record: DatabaseEnum, record_to_datei: str
    ):
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{record_to_datei}"
        )

    def query(self) -> Paginator[Page]:
        return self.record_db.query(filter=self.record_to_datei.filter.is_not_empty())

    def process_page(self, record: Page) -> None:
        if record.parent != self.record_db:
            return
        if not (datei_list := record.properties[self.record_to_datei]):
            return
        if new_title := self.date_namespace.prepend_date_in_record_title(
            record.retrieve(), datei_list, self.check_needs_separator(record)
        ):
            properties = PageProperties()
            properties[record.properties.title_prop] = new_title
            record.update(properties)
            logger.info(f"{record} -> {properties}")

    @staticmethod
    def check_needs_separator(record: Page) -> bool:
        if record.parent == DatabaseEnum.stage_db.entity:
            return record.properties[work_needs_sch_datei_prop]
        return True


class CopyRecordRel(MatchSequentialAction):
    def __init__(
        self, base: MatchActionBase, record: DatabaseEnum, dst_prop: str, src_prop: str
    ):
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei_prop = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{dst_prop}"
        )
        self.record_to_src_datei_prop = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{src_prop}"
        )

    def __repr__(self):
        return repr_object(self, record_db=self.record_db)

    def query(self) -> Iterable[Page]:
        return self.record_db.query(self.record_to_src_datei_prop.filter.is_not_empty())

    def process_page(self, record: Page) -> Any:
        if not (record.parent == self.record_db):
            return
        record_datei = record.properties[self.record_to_datei_prop]
        record_datei_new = (
            record_datei + record.properties[self.record_to_src_datei_prop]
        )
        if record_datei == record_datei_new:
            logger.info(f"{record} : Skipped")
            return
        record.update(PageProperties({self.record_to_datei_prop: record_datei_new}))


class MatchReadingStartDatei(MatchSequentialAction):
    def __init__(self, base: MatchActionBase):
        super().__init__(base)
        self.reading_db = DatabaseEnum.read_db.entity
        self.event_db = DatabaseEnum.event_db.entity

    def query(self) -> Paginator[Page]:
        return self.reading_db.query(
            reading_to_start_date_prop.filter.is_empty()
            & (
                reading_to_event_prop.filter.is_not_empty()
                | reading_to_date_prop.filter.is_not_empty()
                | reading_match_date_by_created_time_prop.filter.is_not_empty()
            )
        )

    def process_page(self, reading: Page) -> None:
        if not (
            reading.parent == self.reading_db
            and not reading.properties[reading_to_start_date_prop]
        ):
            return

        datei = self.find_datei(reading)
        if not datei:
            logger.info(f"{reading} : Skipped")
            return
        # final check if the property value is filled in the meantime
        if reading.retrieve().properties[reading_to_start_date_prop]:
            logger.info(f"{reading} : Skipped")
            return
        reading.update(
            PageProperties(
                {
                    reading_to_start_date_prop: reading_to_start_date_prop.page_value(
                        [datei]
                    )
                }
            )
        )
        logger.info(f"{reading} - {reading_to_date_prop.name} : {datei}")

    def find_datei(self, reading: Page) -> Optional[Page]:
        def get_reading_event_dates() -> Iterable[Page]:
            reading_event_progs = reading.properties[reading_to_event_prop]
            for event in reading_event_progs:
                if date_list := event.properties[record_to_datei_prop]:
                    yield date_list[0]

        if reading_event_datei_set := {*get_reading_event_dates()}:
            return Datei.get_earliest(reading_event_datei_set)
        if reading_relevant_date := reading.properties[record_to_sch_datei_prop]:
            return Datei.get_earliest(reading_relevant_date)
        if (
            datei_by_title := self.date_namespace.get_page_by_record_title(
                reading.properties.title.plain_text
            )
        ) is not None:
            return datei_by_title
        if reading.properties[reading_match_date_by_created_time_prop]:
            reading_created_date = get_record_created_date(reading)
            return self.date_namespace.get_page_by_date(reading_created_date)


class MatchRecordTimestr(MatchSequentialAction):
    def __init__(
        self, base: MatchActionBase, record: DatabaseEnum, record_to_date: str
    ):
        super().__init__(base)
        self.record_db = record.entity
        self.record_to_datei = RelationProperty(
            DatabaseEnum.dateid_db.prefix + record_to_date
        )

    def __repr__(self):
        return repr_object(
            self, record_db=self.record_db, record_to_datei=self.record_to_datei
        )

    def query(self) -> Iterable[Page]:
        # since the benefits are concentrated on near present days,
        # we could easily limit query() with today without lamentations
        return self.record_db.query(
            record_timestr_prop.filter.is_empty()
            & created_time_filter.equals(dt.date.today())
        )

    def will_process(self, record: Page) -> bool:
        if not (
            record.parent == self.record_db
            and not record.properties[record_timestr_prop]
        ):
            return False
        try:
            return record.properties["⚙️📆일지"]
        except KeyError:
            pass
        try:
            record_dateid = record.properties[self.record_to_datei][0]
        except IndexError:
            return True
        record_dateid_date = record_dateid.properties[datei_date_prop]
        if record_dateid_date is None:
            return False
        return record.created_time.date() == record_dateid_date.start

    def process_page(self, record: Page) -> None:
        if not self.will_process(record):
            return
        timestr = record.created_time.strftime("%H:%M")
        if record.retrieve().properties[record_timestr_prop]:
            logger.info(f"{record} : Skipped")
            return
        record.update(
            PageProperties(
                {
                    record_timestr_prop: record_timestr_prop.page_value(
                        [TextSpan(timestr)]
                    )
                }
            )
        )
        logger.info(f"{record} : {timestr}")


class MatchRecordWeekiByDatei(MatchSequentialAction):
    def __init__(
        self,
        base: MatchActionBase,
        record_db_enum: DatabaseEnum,
        record_to_week: str,
        record_to_date: str,
    ):
        super().__init__(base)
        self.record_db = record_db_enum.entity
        self.record_db_title = record_db_enum.title
        self.record_to_weeki = RelationProperty(
            f"{DatabaseEnum.weekid_db.prefix}{record_to_week}"
        )
        self.record_to_datei = RelationProperty(
            f"{DatabaseEnum.dateid_db.prefix}{record_to_date}"
        )

    def __repr__(self):
        return repr_object(
            self,
            record_db_title=self.record_db_title,
            record_to_weeki=self.record_to_weeki,
            record_to_datei=self.record_to_datei,
        )

    def query(self) -> Paginator[Page]:
        return self.record_db.query(
            self.record_to_weeki.filter.is_empty()
            & self.record_to_datei.filter.is_not_empty()
        )

    def process_page(self, record: Page) -> None:
        if not (
            record.parent == self.record_db and record.properties[self.record_to_datei]
        ):
            return

        new_record_weeks = self.record_to_weeki.page_value()
        for record_date in record.properties[self.record_to_datei]:
            try:
                new_record_weeks.append(record_date.properties[datei_to_weeki_prop][0])
            except IndexError:
                pass  # TODO: add warning

        # final check if the property value is filled or changed in the meantime
        prev_record_weeks = record.properties[self.record_to_weeki]
        if set(prev_record_weeks) == set(new_record_weeks):
            logger.info(f"{record} : Skipped")
            return

        curr_record_weeks = record.retrieve().properties[self.record_to_weeki]
        if (set(prev_record_weeks) != set(curr_record_weeks)) or (
            set(curr_record_weeks) == set(new_record_weeks)
        ):
            logger.info(f"{record} : Skipped")
            return
        record.update(PageProperties({self.record_to_weeki: new_record_weeks}))
        logger.info(f"{record} : {list(new_record_weeks)}")
        return


class MatchDatei(MatchSequentialAction):
    def __init__(self, base: MatchActionBase):
        super().__init__(base)
        self.date_db = DatabaseEnum.dateid_db.entity

    def __repr__(self):
        return repr_object(self)

    def query(self) -> Paginator[Page]:
        return self.date_db.query(
            datei_date_prop.filter.is_empty() or datei_to_weeki_prop.filter.is_empty()
        )

    def process_page(self, datei: Page) -> None:
        if datei.parent != self.date_db:
            return
        properties = PageProperties()

        # match date
        if date_range := datei.properties[datei_date_prop]:
            date = date_range.start
        else:
            date = self.date_namespace.get_date_of_title(
                datei.properties.title.plain_text
            )
            properties[datei_date_prop] = datei_date_prop.page_value(
                start=date, end=None
            )

        # match weeki
        weeki = self.week_namespace.get_page_by_date(date)
        if not datei.retrieve().properties[datei_to_weeki_prop]:
            properties[datei_to_weeki_prop] = datei_to_weeki_prop.page_value([weeki])

        # match title
        day_name = korean_weekday[date.weekday()] + "요일"
        title_plain_text = f'{date.strftime("%y%m%d")} {day_name}'
        if datei.title.plain_text != title_plain_text:
            properties[datei.properties.title_prop] = (
                datei.properties.title_prop.page_value.from_plain_text(title_plain_text)
            )

        if properties:
            logger.info(f"{datei} -> {properties}")
            datei.update(properties=properties)
        else:
            logger.info(f"{datei} : Skipped")


class CopyEventRelsToTarget(MatchSequentialAction):
    event_db = DatabaseEnum.event_db.entity

    def __init__(self, base: MatchActionBase, target_db_enum: DatabaseEnum):
        super().__init__(base)
        self.target_db = target_db_enum.entity
        self.event_to_target_prop = RelationProperty(target_db_enum.prefix_title)

    def __repr__(self):
        return repr_object(self, target_db=self.target_db)

    def query(self) -> Iterable[Page]:
        return self.event_db.query(
            filter=self.event_to_target_prop.filter.is_not_empty()
        )

    def process_page(self, event: Page) -> Any:
        if event.parent != self.event_db:
            return
        self.event_to_target_prop: RelationProperty
        target_list = event.properties[self.event_to_target_prop]
        if not target_list:
            return
        target = target_list[0]
        target_new_properties = PageProperties()

        for rel_prop in [
            record_to_datei_prop,
            record_to_intent_prop,
            record_to_extent_prop,
            record_to_stage_prop,
            record_to_tide_prop,
            record_to_read_prop,
            record_to_tap_prop,
            record_to_journal_prop,
        ]:
            if self.event_db.properties[rel_prop].database == self.target_db:
                try:
                    target_rel_prop = next(
                        prop
                        for prop in [
                            RelationProperty(
                                self.target_db.icon.as_emoji_value() + lower
                            ),
                            RelationProperty(
                                self.target_db.icon.as_emoji_value() + relevant
                            ),
                            rel_prop,
                        ]
                        if prop in self.target_db.properties
                    )
                except StopIteration:
                    raise RuntimeError(
                        f"cannot find self-relation prop, {self.target_db=}"
                    )
            else:
                target_rel_prop = rel_prop
            event_rel_value_list = event.properties[rel_prop]
            target_rel_value_list_prev = target.properties[target_rel_prop]
            target_rel_value_list_new = (
                target_rel_value_list_prev + event_rel_value_list
            )
            if target_rel_value_list_new != target_rel_value_list_prev:
                target_new_properties[target_rel_prop] = target_rel_value_list_new

        if not target_new_properties:
            logger.info(f"{target} <--Copy-- progress {event} : Skipped")
            return
        logger.info(f"{target} <--Copy-- progress {event} : {target_new_properties}")
        target.update(properties=target_new_properties)


class ReplaceMentionToLinks(MatchSequentialAction):
    # TODO: currently unused. find alternative way without editing blocks.
    def __init__(self, base: MatchActionBase, record_db_enum: DatabaseEnum):
        super().__init__(base)
        self.record_db = record_db_enum.entity

    def query(self) -> Iterable[Page]:
        return self.record_db.query(
            filter=record_contents_merged_prop.filter.is_not_empty()
        )

    def process_page(self, page: Page) -> Any:
        if not page.properties[record_contents_merged_prop]:
            logger.info(f"{page}: ReplaceMentionToLinks skipped")
            return
        page.as_block().retrieve_children()


class DatabaseNamespace(metaclass=ABCMeta):
    def __init__(self, database: DatabaseEnum, title_prop: str):
        self.database = database.entity
        self.title_prop = TitleProperty(title_prop)
        self.pages_by_title_plain_text: dict[str, Page] = {}

    def get_page_by_title(self, title_plain_text: str) -> Optional[Page]:
        if page := self.pages_by_title_plain_text.get(title_plain_text):
            return page
        page_list = self.database.query(self.title_prop.filter.equals(title_plain_text))
        if not page_list:
            return None
        page = page_list[0]
        self.pages_by_title_plain_text[page.properties.title.plain_text] = page
        return page


class DateINamespace(DatabaseNamespace):
    def __init__(self):
        super().__init__(DatabaseEnum.dateid_db, EmojiCode.GREEN_BOOK + "제목")

    def get_page_by_date(self, date: dt.date) -> Page:
        day_name = korean_weekday[date.weekday()] + "요일"
        title_plain_text = f'{date.strftime("%y%m%d")} {day_name}'
        return self.get_page_by_title(title_plain_text) or self.create_page(
            title_plain_text, date
        )

    def create_page(self, title_plain_text: str, date: dt.date) -> Page:
        page = self.database.create_child_page(
            PageProperties(
                {
                    self.title_prop: self.title_prop.page_value.from_plain_text(
                        title_plain_text
                    ),
                    datei_date_prop: datei_date_prop.page_value(start=date, end=None),
                }
            )
        )
        self.pages_by_title_plain_text[page.properties.title.plain_text] = page
        return page

    @classmethod
    def strf_date(cls, datei: Page) -> str:
        return datei.properties[datei_date_prop].start.strftime("%y%m%d")

    def get_page_by_record_title(self, title_plain_text: str) -> Optional[Page]:
        date = self.get_date_of_title(title_plain_text)
        if date is None:
            return None
        return self.get_page_by_date(date)

    _getter_pattern = re.compile(r"(\d{2})(\d{2})(\d{2}).*")
    _getter_pattern_2 = re.compile(r"(\d{2})(\d{2})(\d{2})[|]")

    @classmethod
    def get_date_of_title(cls, title_plain_text: str) -> Optional[dt.date]:
        match = cls._getter_pattern.match(
            title_plain_text
        ) or cls._getter_pattern_2.search(title_plain_text)
        return parse_yymmdd(match)

    _checker_yymmdd_1 = re.compile(r"(\d{2})(\d{2})(\d{2}).*")
    _checker_yymmdd_2 = re.compile(r"(\d{2})(\d{2})\d{2}-(\d{2})")
    _checker_yymm_1 = re.compile(r"(\d{2})(\d{2})([ -]|$)")
    _checker_yy = re.compile(r"(\d{2})([ -]|$)")

    @classmethod
    def _check_date_in_record_title__candidate(
        cls, title_plain_text: str, date_candidates: list[dt.date]
    ) -> bool:
        yymmdd_1 = parse_yymmdd(cls._checker_yymmdd_1.search(title_plain_text))
        if yymmdd_1 in date_candidates:
            return True
        yymmdd_2 = parse_yymmdd(cls._checker_yymmdd_2.search(title_plain_text))
        if yymmdd_2 in date_candidates:
            return True
        return False

    @classmethod
    def _check_date_in_record_title(
        cls, title_plain_text: str
    ) -> bool:
        yymmdd_1 = parse_yymmdd(cls._checker_yymmdd_1.search(title_plain_text))
        if yymmdd_1:
            return True
        yymmdd_2 = parse_yymmdd(cls._checker_yymmdd_2.search(title_plain_text))
        if yymmdd_2:
            return True
        return False

    @classmethod
    def prepend_date_in_record_title(
        cls, record: Page, candidate_datei_list: Iterable[Page], needs_separator: bool
    ) -> RichText:
        """if candidate is many, choose the earliest."""
        title = record.properties.title
        datei_date_list = [
            datei.properties[datei_date_prop].start for datei in candidate_datei_list
        ]

        needs_update = not cls._check_date_in_record_title(
            title.plain_text
        )
        if not needs_update:
            return RichText()

        earliest_datei_date = min(datei_date_list)
        add_separator = needs_separator and ("|" not in title.plain_text)
        starts_with_separator = title.plain_text.startswith("|")
        default_title = ""
        if not title.plain_text:
            add_separator = False
            if record_kind := record.properties.get(record_kind_prop):
                default_title = record_kind.name[-2:]
            else:
                default_title = cast(Database, record.parent).title.plain_text
        return RichText(
            [
                TextSpan(
                    f"{earliest_datei_date.strftime('%y%m%d')}{'|' if add_separator else ''}"
                    f"{'' if starts_with_separator else ' '}"
                    f"{default_title}"
                ),
                *title,
            ]
        )


class WeekINamespace(DatabaseNamespace):
    def __init__(self):
        super().__init__(DatabaseEnum.weekid_db, EmojiCode.GREEN_BOOK + "제목")

    def get_page_by_date(self, date: dt.date) -> Page:
        title_plain_text = self._get_first_day_of_week(date).strftime("%y_%U")
        return self.get_page_by_title(title_plain_text) or self.create_page(
            title_plain_text, date
        )

    def create_page(self, title_plain_text: str, date: dt.date) -> Page:
        page = self.database.create_child_page(
            PageProperties(
                {
                    self.title_prop: self.title_prop.page_value.from_plain_text(
                        title_plain_text
                    ),
                    weeki_date_range_prop: weeki_date_range_prop.page_value(
                        start=self._get_first_day_of_week(date),
                        end=self._get_last_day_of_week(date),
                    ),
                }
            )
        )
        self.pages_by_title_plain_text[page.properties.title.plain_text] = page
        return page

    @classmethod
    def _get_first_day_of_week(cls, date: dt.date) -> dt.date:
        # returns the first day (sunday) of the week.
        weekday = (date.weekday() + 1) % 7
        return date + dt.timedelta(days=-weekday)

    @classmethod
    def _get_last_day_of_week(cls, date: dt.date) -> dt.date:
        return cls._get_first_day_of_week(date) + dt.timedelta(days=6)


def get_record_created_date(record: Page) -> dt.date:
    # TODO: '📆일지' parsing 지원
    return (record.created_time + dt.timedelta(hours=-5)).date()
