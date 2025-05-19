from typing import cast

from loguru import logger

from app.my_block import DatabaseEnum
from notion_df.entity import Page, Database
from notion_df.property import (
    PageProperties,
    RelationProperty,
    RelationPagePropertyValue,
    DualRelationDatabasePropertyValue,
    RelationDatabasePropertyValue,
    DualRelationProperty,
)


def subtract_db(target_db: DatabaseEnum):
    rel_prop1 = RelationProperty("💙연관")
    rel_prop2 = RelationProperty("💙일과")

    for target in target_db.entity.query(rel_prop1.filter.is_not_empty()):
        target_rel1 = target.properties[rel_prop1]
        if target_rel1.has_more:
            # TODO: reuse this when implementing PartialProperty.resolve()
            true_rel_prop1 = target.properties._get_prop(rel_prop1.name)
            target.retrieve_property_item(true_rel_prop1)
            # ENDTODO
        target_rel1_minus_rel2 = (
            target.properties[rel_prop1] - target.properties[rel_prop2]
        )
        if target_rel1 == target_rel1_minus_rel2:
            logger.info(f"skip {target=}")
            continue
        update_page(target, rel_prop1, target_rel1_minus_rel2)


def update_page(
    target: Page, prop: RelationProperty, new_prop_value: RelationPagePropertyValue
):
    # TODO reuse this on core module, "util" method
    max_relation_length = 100

    if len(new_prop_value) <= max_relation_length:
        target.update(
            PageProperties(
                {
                    prop: new_prop_value,
                }
            )
        )
        return
    db_prop_value: RelationDatabasePropertyValue = cast(
        Database, target.parent
    ).properties[prop]
    if not isinstance(db_prop_value, DualRelationDatabasePropertyValue):
        raise RuntimeError(f"{db_prop_value=}")
    target.update(
        PageProperties({prop: prop.page_value(new_prop_value[:max_relation_length])})
    )
    excess_counterpage_list = new_prop_value[max_relation_length:]
    synced_prop: DualRelationProperty = db_prop_value.synced_property
    for counterpage in excess_counterpage_list:
        counterpage.update(
            PageProperties(
                {
                    synced_prop: synced_prop.page_value(
                        counterpage.properties[synced_prop] + [target]
                    )
                }
            )
        )


if __name__ == "__main__":
    for db in [
        DatabaseEnum.stage_db,
        DatabaseEnum.read_db,
        DatabaseEnum.dateid_db,
        DatabaseEnum.weekid_db,
    ]:
        subtract_db(db)
