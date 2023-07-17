import pickle
from collections import defaultdict
from pathlib import Path

from notion_df.entity import Database
from notion_df.property import RelationProperty
from notion_df.variable import Settings
from workflow import data_path
from workflow.main.block_enum import DatabaseEnum

pickle_path: Path = data_path / 'all_relation_properties'


def init():
    with Settings.print:
        _all_relation_properties: dict[tuple[Database, Database], list[RelationProperty]] = defaultdict(list)
        for db_enum in DatabaseEnum:
            db = db_enum.entity
            db.retrieve()
            for prop in db.properties:
                if isinstance(prop, RelationProperty):
                    from typing import cast
                    linked_db = cast(prop.database_value, db.properties[prop]).database
                    _all_relation_properties[(db, linked_db)].append(prop)
    pickle.dump(_all_relation_properties, pickle_path.open('wb'))


def get_all_relation_properties():
    all_relation_properties = pickle.load(pickle_path.open('rb'))
    return all_relation_properties


def get_multiple():
    for (db, linked_db), prop_list in get_all_relation_properties().items():
        if len(prop_list) > 1 and db.title.plain_text < linked_db.title.plain_text and DatabaseEnum.from_entity(
                db) and DatabaseEnum.from_entity(db).name.find('depr') == -1:
            print(db.title.plain_text, linked_db.title.plain_text, prop_list)


def get_date():
    for (db, linked_db), prop_list in get_all_relation_properties().items():
        db_enum = DatabaseEnum.from_entity(db)
        linked_db_enum = DatabaseEnum.from_entity(linked_db)
        if linked_db_enum in (DatabaseEnum.date_db,):
            print(db_enum.prefix_title, linked_db_enum.prefix_title, sorted(prop.name for prop in prop_list))


def get_week():
    for (db, linked_db), prop_list in get_all_relation_properties().items():
        db_enum = DatabaseEnum.from_entity(db)
        linked_db_enum = DatabaseEnum.from_entity(linked_db)
        if linked_db_enum in (DatabaseEnum.week_db,):
            print(db_enum.prefix_title, linked_db_enum.prefix_title, sorted(prop.name for prop in prop_list))


if __name__ == '__main__':
    init()
    get_date()
    print('----')
    get_week()

