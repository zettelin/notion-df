from functools import cache
from pathlib import Path
from typing import Optional, cast, Iterator, Iterable

import tenacity
from loguru import logger

from notion_df.core.request_base import RequestError
from notion_df.entity import Page, Database
from notion_df.data import PageData
from notion_df.property import RelationProperty, PageProperties, RelationDatabasePropertyValue, \
    DualRelationDatabasePropertyValue
from workflow.action.match import get_earliest_date
from workflow.block import DatabaseEnum, schedule, start, common, elements, related
from workflow.core.action import SequentialAction
from workflow.service.backup_service import ResponseBackupService


class MigrationBackupSaveAction(SequentialAction):
    def __init__(self, backup_dir: Path):
        self.backup = ResponseBackupService(backup_dir)

    def query(self) -> Iterable[Page]:
        return []

    def process_page(self, page: Page) -> None:
        if not isinstance(page.data.parent, Database):
            return
        for prop in page.data.properties:
            if not isinstance(prop, RelationProperty):
                continue
            prop_value = page.data.properties[prop]
            # TODO: resolve Notion 504 error
            #  https://notiondevs.slack.com/archives/C01CZTMG85C/p1701409539104549
            if prop_value.has_more:
                try:
                    page.retrieve_property_item(prop)
                except tenacity.RetryError:
                    logger.error(f'failed Page.retrieve_property_item({page}, prop={prop.name})')
                    raise RuntimeError(f'failed Page.retrieve_property_item({page}, prop={prop.name})')
        self.backup.write(page)


class MigrationBackupLoadAction(SequentialAction):
    def __init__(self, backup_dir: Path):
        self.response_backup = ResponseBackupService(backup_dir)

    def query(self) -> Iterable[Page]:
        return []

    def process_page(self, end_page: Page) -> None:
        # this_page: the global page, directly under one of the global dbs
        this_page = next((breadcrumb_page for breadcrumb_page in iter_breadcrumb(end_page)
                          if DatabaseEnum.from_entity(breadcrumb_page.data.parent) is not None), None)
        if this_page is None:
            logger.info(f'\t{end_page}: Moved outside DatabaseEnum')

        this_db: Database = this_page.data.parent
        this_prev_data: Optional[PageData] = self.response_backup.read(end_page)
        if not this_prev_data:
            logger.info(f'\t{end_page}: No previous response backup')
            return
        this_prev_db = this_prev_data.parent
        if end_page == this_page and this_prev_db == this_db:
            logger.info(f'\t{end_page}: Did not change the parent database')
            return

        this_new_properties = PageProperties()
        for this_prev_prop, this_prev_prop_value in this_prev_data.properties.items():
            if not isinstance(this_prev_prop, RelationProperty):
                continue
            for linked_page in cast(Iterable[Page], this_prev_prop_value):

                linked_prev_data: PageData = self.response_backup.read(linked_page)
                if linked_page.data:
                    linked_db = linked_page.data.parent
                    if linked_prev_data:
                        linked_prev_db = linked_prev_data.parent
                    else:
                        linked_prev_db = None
                elif linked_prev_data:
                    linked_db = linked_prev_db = linked_prev_data.parent
                else:
                    logger.info(f"Retrieve because initial data missing - {linked_page=}")
                    linked_db = linked_prev_db = linked_page.get_data().parent
                candidate_props = self.get_candidate_props(this_db, linked_db)
                if not candidate_props:
                    continue
                if any(linked_page in this_page.data.properties[prop] for prop in candidate_props):
                    continue
                new_prop: RelationProperty = self.find_new_relation_property(this_db, this_prev_db, linked_db,
                                                                             linked_prev_db, this_prev_prop)
                if not new_prop:
                    continue
                if new_prop not in this_new_properties:
                    if this_page.data.properties[new_prop].has_more:
                        this_page.retrieve_property_item(new_prop)
                    this_new_properties[new_prop] = this_page.data.properties[new_prop]
                this_new_properties[new_prop].append(linked_page)
        # TODO: manually remove relation to itself
        for this_new_prop in this_new_properties:
            if any(stem in this_new_prop.name for stem in [start, ]):
                dates = cast(RelationProperty.page_value, this_new_properties[this_new_prop])
                this_new_properties[this_new_prop] = RelationProperty.page_value([get_earliest_date(dates)])
        if not this_new_properties:
            return
        try:
            logger.info(f'\t{this_page}: {this_new_properties}')
            this_page.update(this_new_properties)
            return
        except RequestError as e:
            if (e.code == 'object_not_found') or ('Unsaved transactions' in e.message):
                for prop in this_new_properties:
                    this_new_properties[prop] = RelationProperty.page_value(
                        page for page in this_new_properties[prop] if page_exists(page))
                this_page.update(this_new_properties)
                logger.info(f'\tRETRY {this_page}: {this_new_properties}')
            elif 'relation.length should be ≤ `100`' in e.message:
                excess_page_dict = {}
                for prop in this_new_properties:
                    prop: RelationProperty
                    if len(this_new_properties[prop]) > 100:
                        excess_page_dict[prop] = this_new_properties[prop][100:]
                        this_new_properties[prop] = prop.page_value(this_new_properties[prop][:100])
                this_page.update(this_new_properties)
                for prop, excess_pages in excess_page_dict.items():
                    db_prop_value: RelationDatabasePropertyValue = \
                    cast(Database, this_page.data.parent).get_data().properties[prop]
                    if not isinstance(db_prop_value, DualRelationDatabasePropertyValue):
                        raise e
                    synced_prop = db_prop_value.synced_property
                    for that_page in excess_pages:
                        that_page.update(PageProperties({synced_prop: synced_prop.page_value(
                            that_page.get_data().properties[synced_prop] + [this_page]
                        )}))
            else:
                logger.error(f'\tFAILED {this_page}: {this_new_properties}')
                raise e

    @classmethod
    @cache
    def get_candidate_props(cls, this_db: Database, linked_db: Database) -> list[RelationProperty]:
        candidate_props: list[RelationProperty] = []
        for prop in this_db.data.properties:
            if not isinstance(prop, RelationProperty):
                continue
            if this_db.data.properties[prop].database == linked_db:
                candidate_props.append(prop)
        return candidate_props

    @classmethod
    def find_new_relation_property(
            cls, this_db: Database, this_prev_db: Optional[Database],
            linked_db: Database, linked_prev_db: Optional[Database],
            this_prev_prop: RelationProperty) -> Optional[RelationProperty]:
        """this method guarantee that the returning property is picked from its candidates (this_db.properties)"""
        # TODO: if candidate_props is empty, create a mention-backlink instead
        # TODO: error handling on unique relational limit (provide related pages list on error message, etc.)
        this_db_enum = DatabaseEnum.from_entity(this_db)
        this_prev_db_enum = DatabaseEnum.from_entity(this_prev_db)
        linked_db_enum = DatabaseEnum.from_entity(linked_db)
        linked_prev_db_enum = DatabaseEnum.from_entity(linked_prev_db)
        candidate_props = cls.get_candidate_props(this_db, linked_db)

        def pick(_prop_name: str) -> Optional[RelationProperty]:
            return next((_prop for _prop in candidate_props if _prop_name in _prop.name), None)

        # customized cases
        if linked_db_enum == DatabaseEnum.datei_db:
            prefix = DatabaseEnum.datei_db.prefix
            prefix_title = DatabaseEnum.datei_db.prefix_title
            if this_prev_prop.name in [prefix_title, f'{prefix}{schedule}', f'{prefix}{start}']:
                return pick(this_prev_prop.name) or pick(prefix_title)
        if linked_db_enum == DatabaseEnum.weeki_db:
            prefix = DatabaseEnum.weeki_db.prefix
            prefix_title = DatabaseEnum.datei_db.prefix_title
            if this_prev_prop.name in [prefix_title, f'{prefix}{schedule}', f'{prefix}{start}']:
                return pick(this_prev_prop.name) or pick(prefix_title)
        if this_db_enum == linked_db_enum and this_prev_db_enum == linked_prev_db_enum:
            for prop_name_stem in [common, elements, related]:
                if (prop_name_stem in this_prev_prop.name) and (prop_name := pick(prop_name_stem)):
                    return prop_name
        if this_db_enum == DatabaseEnum.issue_db and linked_db_enum == DatabaseEnum.issue_db:
            if this_prev_db_enum == DatabaseEnum.area_db:
                return pick(elements)
        if this_db_enum == DatabaseEnum.area_db and linked_db_enum == DatabaseEnum.area_db:
            if this_prev_db_enum == DatabaseEnum.idea_db:
                return pick(elements)
            return pick(common)

        # default cases
        if linked_db_enum:
            if prop := pick(linked_db_enum.prefix_title):
                return prop
        return candidate_props[0]


# TODO: integrate to base package
def iter_breadcrumb(page: Page) -> Iterator[Page]:
    page.data
    yield page
    if page.data.parent is not None:
        yield from iter_breadcrumb(page.data.parent)


# TODO: integrate to base package
def page_exists(page: Page) -> bool:
    try:
        page.data
        return True
    except RequestError:
        return False
