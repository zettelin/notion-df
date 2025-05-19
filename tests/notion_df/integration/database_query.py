from datetime import date
from pprint import pprint

from notion_df.entity import Database
from notion_df.misc import DateRange
from notion_df.property import DateProperty, URLProperty

if __name__ == "__main__":
    database = Database(
        "https://www.notion.so/dyhn/961d1ca0a3d24a46b838ba85e710f18d?v=c88ba6af32e249c99aef15d7b8044bdf&pvs=4"
    )
    my_date_equals_20230101 = DateProperty("📆날짜").filter.equals(date(2023, 1, 1))
    pages = database.query(my_date_equals_20230101, page_size=10)
    pprint(pages)
    page_properties = pages[0].data.properties
    url = page_properties[URLProperty("url")]
    url2 = page_properties["url"]
    daterange = page_properties[DateProperty("date")]
    page_properties[DateProperty("date")] = DateRange(
        date(2023, 1, 1), date(2023, 1, 2)
    )
    # page_properties[DateProperty('date')] = 2
