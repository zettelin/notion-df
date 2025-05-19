from notion_df.entity import Page

if __name__ == "__main__":
    page = Page("https://www.notion.so/dyhn/24-09-103063001c5e8050a53eec832c045f19")
    print(page.parent.title)
