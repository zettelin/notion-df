from pprint import pprint

from notion_df.entity import Database

if __name__ == "__main__":
    database: Database = Database(
        "https://www.notion.so/dyhn/961d1ca0a3d24a46b838ba85e710f18d?v=c88ba6af32e249c99aef15d7b8044bdf&pvs=4"
    )
    database.retrieve()
    pprint(database)
