from pprint import pprint

from notion_df.entity import Workspace

if __name__ == "__main__":
    result = Workspace().search_by_title("", None, "descending", page_size=5)
    pprint(result)
    pprint(result[:10])
