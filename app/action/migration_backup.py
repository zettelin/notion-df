from functools import cache
from pathlib import Path
from typing import Optional, cast, Iterator, Iterable

import tenacity
from loguru import logger

from app.action.__core__ import SequentialAction
from app.my_block import (
    DatabaseEnum,
    schedule,
    start,
    upper,
    lower,
    relevant,
    Datei,
    Weeki,
)
from app.service.backup_service import ResponseBackupService
from notion_df.contents import ParagraphBlockContents
from notion_df.core.request_core import RequestError
from notion_df.data import PageData
from notion_df.entity import Page, Database, Block
from notion_df.property import (
    RelationProperty,
    PageProperties,
    RelationDatabasePropertyValue,
    DualRelationDatabasePropertyValue,
)
from notion_df.rich_text import PageMention, RichText


class MigrationBackupSaveAction(SequentialAction):
    def __init__(self, backup_dir: Path):
        self.backup = ResponseBackupService(backup_dir)

    def query(self) -> Iterable[Page]:
        return []

    def process_page(self, page: Page) -> None:
        # TODO: add database backup
        if not isinstance(page.parent, Database):
            return
        for prop in page.properties:
            if not isinstance(prop, RelationProperty):
                continue
            prop_value = page.properties[prop]
            # TODO: resolve Notion 504 error
            #  https://notiondevs.slack.com/archives/C01CZTMG85C/p1701409539104549
            if prop_value.has_more:
                try:
                    page.retrieve_property_item(prop)
                except tenacity.RetryError:
                    logger.error(
                        f"failed Page.retrieve_property_item({page}, prop={prop.name})"
                    )
                    raise RuntimeError(
                        f"failed Page.retrieve_property_item({page}, prop={prop.name})"
                    )
        self.backup.write(page)


class MigrationBackupLoadAction(SequentialAction):
    def __init__(self, backup_dir: Path):
        self.response_backup = ResponseBackupService(backup_dir)
        # TODO: load database backup as preview data

    def query(self) -> Iterable[Page]:
        return []

    def process_page(self, end_page: Page) -> None:
        # this_page: the global page, directly under one of the global dbs
        this_page: Page = next(
            (
                breadcrumb_page
                for breadcrumb_page in iter_breadcrumb(end_page)
                if isinstance(breadcrumb_page.parent, Database)
                # if DatabaseEnum.from_entity(breadcrumb_page.parent) is not None
            ),
            None,
        )
        if this_page is None:
            logger.info(f"\t{end_page}: Moved outside DatabaseEnum")
            return

        this_db: Database = this_page.parent
        this_prev_data: Optional[PageData] = self.response_backup.read(end_page)
        if not this_prev_data:
            logger.info(f"\t{end_page}: No previous response backup")
            return
        this_prev_db = this_prev_data.parent
        if end_page == this_page and this_prev_db == this_db:
            logger.info(f"\t{end_page}: Did not change the parent database")
            return

        this_new_properties = PageProperties()
        new_mention_page_list = []
        for this_prev_prop, this_prev_prop_value in this_prev_data.properties.items():
            if not isinstance(this_prev_prop, RelationProperty):
                continue
            for linked_page in cast(Iterable[Page], this_prev_prop_value):
                linked_prev_data: Optional[PageData] = self.response_backup.read(
                    linked_page
                )
                if not linked_prev_data:
                    logger.info(f"\t{linked_page=}: No previous response backup")
                    continue
                if linked_page.local_data:
                    linked_db = linked_page.parent
                    if linked_prev_data:
                        linked_prev_db = linked_prev_data.parent
                    else:
                        linked_prev_db = None
                else:
                    linked_db = linked_prev_db = linked_prev_data.parent
                candidate_props = self.get_candidate_props(this_db, linked_db)
                if not candidate_props:
                    new_mention_page_list.append(linked_page)
                    continue
                if any(
                    linked_page in this_page.properties[prop]
                    for prop in candidate_props
                ):
                    continue
                new_prop: RelationProperty = self.find_new_relation_property(
                    this_db, this_prev_db, linked_db, linked_prev_db, this_prev_prop
                )
                if not new_prop:
                    new_mention_page_list.append(linked_page)
                    continue
                if new_prop not in this_new_properties:
                    if this_page.properties[new_prop].has_more:
                        this_page.retrieve_property_item(new_prop)
                    this_new_properties[new_prop] = this_page.properties[new_prop]
                this_new_properties[new_prop].append(linked_page)
        # TODO: manually remove relation to itself
        for this_new_prop in this_new_properties:
            this_new_prop: RelationProperty
            # TODO: lookup the db property' relevant "unique constraint" field
            if (start in this_new_prop.name) or (
                this_page.parent == DatabaseEnum.event_db.entity
                and this_new_prop.name
                in [
                    DatabaseEnum.dateid_db.prefix_title,
                    DatabaseEnum.weekid_db.prefix_title,
                ]
            ):
                timei_list = this_new_properties[this_new_prop]
                if not timei_list:
                    raise RuntimeError(f"{this_page=}, {this_new_prop=}")
                match timei_list[0].parent:
                    case DatabaseEnum.dateid_db.entity:
                        earliest_timei = Datei.get_earliest(timei_list)
                    case DatabaseEnum.weekid_db.entity:
                        earliest_timei = Weeki.get_earliest(timei_list)
                    case _:
                        raise RuntimeError(
                            f"{this_page=}, {this_new_prop=}, {timei_list[0].parent=}"
                        )
                this_new_properties[this_new_prop] = RelationProperty.page_value(
                    [earliest_timei]
                )
        if not this_new_properties and not new_mention_page_list:
            return
        try:
            logger.info(
                f"\t{this_page}: {this_new_properties=}, {new_mention_page_list=}"
            )
            this_page.update(this_new_properties)
            this_page.as_block().append_children(
                [
                    ParagraphBlockContents(RichText([PageMention(linked_page)]))
                    for linked_page in new_mention_page_list
                ]
            )
            return
        except RequestError as e:
            if (e.code == "object_not_found") or ("Unsaved transactions" in e.message):
                for prop in this_new_properties:
                    this_new_properties[prop] = RelationProperty.page_value(
                        page for page in this_new_properties[prop] if page_exists(page)
                    )
                this_page.update(this_new_properties)
                logger.info(f"\tRETRY {this_page}: {this_new_properties}")
            elif "relation.length should be ≤ `100`" in e.message:
                excess_page_dict = {}
                for prop in this_new_properties:
                    prop: RelationProperty
                    if len(this_new_properties[prop]) > 100:
                        excess_page_dict[prop] = this_new_properties[prop][100:]
                        this_new_properties[prop] = prop.page_value(
                            this_new_properties[prop][:100]
                        )
                this_page.update(this_new_properties)
                for prop, excess_pages in excess_page_dict.items():
                    db_prop_value: RelationDatabasePropertyValue = cast(
                        Database, this_page.parent
                    ).properties[prop]
                    if not isinstance(db_prop_value, DualRelationDatabasePropertyValue):
                        raise e
                    synced_prop = db_prop_value.synced_property
                    for that_page in excess_pages:
                        that_page.update(
                            PageProperties(
                                {
                                    synced_prop: synced_prop.page_value(
                                        that_page.properties[synced_prop] + [this_page]
                                    )
                                }
                            )
                        )
            else:
                logger.error(f"\tFAILED {this_page}: {this_new_properties}")
                raise e

    @classmethod
    @cache
    def get_candidate_props(
        cls, this_db: Database, linked_db: Database
    ) -> list[RelationProperty]:
        candidate_props: list[RelationProperty] = []
        for prop in this_db.properties:
            if not isinstance(prop, RelationProperty):
                continue
            if this_db.properties[prop].database == linked_db:
                candidate_props.append(prop)
        return candidate_props

    @classmethod
    def find_new_relation_property(
        cls,
        this_db: Database,
        this_prev_db: Optional[Database],
        linked_db: Database,
        linked_prev_db: Optional[Database],
        this_prev_prop: RelationProperty,
    ) -> Optional[RelationProperty]:
        """this method guarantee that the returning property is picked from its candidates (this_db.properties)"""
        # TODO: if candidate_props is empty, create a mention-backlink instead
        # TODO: error handling on unique relational limit (provide related pages list on error message, etc.)
        this_db_enum = DatabaseEnum.from_entity(this_db)
        this_prev_db_enum = DatabaseEnum.from_entity(this_prev_db)
        linked_db_enum = DatabaseEnum.from_entity(linked_db)
        linked_prev_db_enum = DatabaseEnum.from_entity(linked_prev_db)
        candidate_props = cls.get_candidate_props(this_db, linked_db)

        def pick(_prop_name: str) -> Optional[RelationProperty]:
            return next(
                (_prop for _prop in candidate_props if _prop_name in _prop.name), None
            )

        # customized cases
        if linked_db_enum == DatabaseEnum.dateid_db:
            prefix = DatabaseEnum.dateid_db.prefix
            prefix_title = DatabaseEnum.dateid_db.prefix_title
            if this_prev_prop.name in [
                prefix_title,
                f"{prefix}{schedule}",
                f"{prefix}{start}",
            ]:
                return pick(this_prev_prop.name) or pick(prefix_title)
        if linked_db_enum == DatabaseEnum.weekid_db:
            prefix = DatabaseEnum.weekid_db.prefix
            prefix_title = DatabaseEnum.dateid_db.prefix_title
            if this_prev_prop.name in [
                prefix_title,
                f"{prefix}{schedule}",
                f"{prefix}{start}",
            ]:
                return pick(this_prev_prop.name) or pick(prefix_title)
        if this_db_enum == linked_db_enum and this_prev_db_enum == linked_prev_db_enum:
            for prop_name_stem in [upper, lower, relevant]:
                if (prop_name_stem in this_prev_prop.name) and (
                    prop_name := pick(prop_name_stem)
                ):
                    return prop_name
        if (
            this_db_enum == DatabaseEnum.tide_db
            and linked_db_enum == DatabaseEnum.tide_db
        ):
            if this_prev_db_enum == DatabaseEnum.extent_db:
                return pick(lower)
        if (
            this_db_enum == DatabaseEnum.extent_db
            and linked_db_enum == DatabaseEnum.extent_db
        ):
            if this_prev_db_enum == DatabaseEnum.tap_db:
                return pick(lower)
            return pick(upper)

        # default cases
        if linked_db_enum:
            if prop := pick(linked_db_enum.prefix_title):
                return prop
        return candidate_props[0]


# TODO: integrate to base package
def iter_breadcrumb(page: Page) -> Iterator[Page | Block | Database]:
    yield page
    if page.parent is not None:
        yield from iter_breadcrumb(page.parent)


# TODO: integrate to base package
def page_exists(page: Page) -> bool:
    try:
        # noinspection PyStatementEffect
        page.data
        return True
    except RequestError:
        return False
