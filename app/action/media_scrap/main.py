import re
from typing import Optional, Callable, Any, Iterable, cast

from loguru import logger
from selenium.webdriver.chrome.webdriver import WebDriver

from app.action.media_scrap.gy_lib_scraper import GYLibraryScraper, LibraryScrapResult
from app.action.media_scrap.yes24_scraper import (
    get_yes24_detail_page_url,
    Yes24ScrapResult,
)
from app.action.__core__ import IndividualAction
from app.my_block import DatabaseEnum
from app.service.webdriver_service import WebDriverService
from notion_df.constant import BlockColor
from notion_df.contents import (
    BlockContents,
    Heading1BlockContents,
    Heading2BlockContents,
    Heading3BlockContents,
    ParagraphBlockContents,
)
from notion_df.contents import ChildPageBlockContents, TableOfContentsBlockContents
from notion_df.core.collection import StrEnum, peek, Paginator
from notion_df.entity import Page
from notion_df.filter import CompoundFilter
from notion_df.misc import Annotations, SelectOption
from notion_df.property import (
    SelectProperty,
    CheckboxFormulaProperty,
    TitleProperty,
    RichTextProperty,
    URLProperty,
    NumberProperty,
    FilesProperty,
    CheckboxProperty,
    PageProperties,
)
from notion_df.rich_text import RichText, TextSpan

edit_status_prop = SelectProperty("📘준비")
media_type_prop = SelectProperty("📘유형")
is_book_prop = CheckboxFormulaProperty("📔도서류")
title_prop = TitleProperty("📙제목")
true_name_prop = RichTextProperty("📚제목")
sub_name_prop = RichTextProperty("📚부제")
url_prop = URLProperty("📚링크")
author_prop = RichTextProperty("📚만든이")
publisher_prop = RichTextProperty("📚만든곳")
volume_prop = NumberProperty("📚분량#")
cover_image_prop = FilesProperty("📚표지")
location_prop = RichTextProperty("📚위치")
not_available_prop = CheckboxProperty("📚대출중")
link_to_contents_prop = RichTextProperty("📦결속")


class EditStatusValue(StrEnum):
    default = "📥본문/위치(비파괴)"
    metadata_overwrite = "📥본문(파괴)"
    location_overwrite = "📥위치(파괴)"
    complete = "⛳수합 완료"
    fill_manually = "👤직접 입력"
    confirm_manually = "👤결과 검정"


class MediaScrapAction(IndividualAction):
    def __init__(self, *, create_window: bool):
        self.reading_db = DatabaseEnum.read_db.entity
        self.driver_service = WebDriverService(create_window=create_window)

    def query(self) -> Paginator[Page]:
        return self.reading_db.query(
            is_book_prop.filter.equals(True)
            & CompoundFilter(
                "or",
                [
                    edit_status_prop.filter.equals(option)
                    for option in [
                        EditStatusValue.default,
                        EditStatusValue.metadata_overwrite,
                        EditStatusValue.location_overwrite,
                        None,
                    ]
                ],
            )
        )

    def filter(self, page: Page) -> bool:
        return (
            page.parent == self.reading_db
            and page.properties[is_book_prop]
            and (
                page.properties[edit_status_prop]
                in [
                    EditStatusValue.default,
                    EditStatusValue.metadata_overwrite,
                    EditStatusValue.location_overwrite,
                    None,
                ]
            )
        )

    def process_pages(self, readings: Iterable[Page]) -> Any:
        readings = (reading for reading in readings if self.filter(reading))
        reading_it = peek(readings)
        if reading_it is None:
            return
        with self.driver_service.create() as driver:
            for reading in reading_it:
                ReadingMediaScraperUnit(reading, driver).execute()
                logger.info(f"\t{reading}")


class ReadingMediaScraperUnit:
    def __init__(self, reading: Page, driver: WebDriver):
        self.driver = driver

        self.reading = reading
        self.new_properties = PageProperties()
        self.callables: list[Callable[[], Any]] = []

        self.title_value = self.reading.properties[title_prop].plain_text
        self.name_value = self.extract_name(self.title_value)
        self.true_name_value = self.reading.properties[true_name_prop].plain_text

    def extract_name(self, title: str) -> str:
        if title.find("_ ") != -1:
            name = title.split("_ ")[1]
        elif title.find(" _") != -1:
            name, author_value = title.split(" _", maxsplit=1)
            # self.new_properties[title_prop] = \
            #    RichTextProperty.page_value.from_plain_text(f'{author_value}_ {name}')
        else:
            name = title
        return name.split("(")[0]

    def execute(self) -> None:
        # TODO: separate content_page title setter as different module
        new_status_value = EditStatusValue.fill_manually
        match getattr(
            self.reading.properties[edit_status_prop], "name", EditStatusValue.default
        ):
            case EditStatusValue.default:
                if self.process_yes24(False) and self.process_lib_gy(False):
                    new_status_value = EditStatusValue.confirm_manually
            case EditStatusValue.metadata_overwrite:
                if self.process_yes24(True):
                    new_status_value = EditStatusValue.complete
            case EditStatusValue.location_overwrite:
                if self.process_lib_gy(True):
                    new_status_value = EditStatusValue.complete
        self.new_properties[edit_status_prop] = SelectOption(new_status_value)
        for _callable in self.callables:
            _callable()
        self.reading.update(self.new_properties)

    def process_yes24(self, overwrite: bool) -> bool:
        def get_url() -> Optional[str]:
            if url_value := self.reading.properties[url_prop]:
                return url_value
            if url_value := get_yes24_detail_page_url(self.true_name_value):
                self.new_properties[url_prop] = url_value
                return url_value
            if url_value := get_yes24_detail_page_url(self.name_value):
                self.new_properties[url_prop] = url_value
                return url_value

        detail_page_url = get_url()
        if not detail_page_url:
            return False
        result = Yes24ScrapResult.scrap(detail_page_url)

        if result.get_true_name():
            self.true_name_value = result.get_true_name()

        new_properties: PageProperties = PageProperties(
            {
                true_name_prop: true_name_prop.page_value.from_plain_text(
                    result.get_true_name()
                ),
                sub_name_prop: sub_name_prop.page_value.from_plain_text(
                    result.get_sub_name()
                ),
                author_prop: author_prop.page_value.from_plain_text(
                    result.get_author()
                ),
                publisher_prop: publisher_prop.page_value.from_plain_text(
                    result.get_publisher()
                ),
                volume_prop: result.get_page_count(),
            }
        )
        if result.get_cover_image_url():
            new_properties[cover_image_prop] = cover_image_prop.page_value.externals(
                [(result.get_cover_image_url(), self.name_value)]
            )
        if not overwrite:
            new_properties = self.filter_not_overwrite(new_properties)
        self.new_properties.update(new_properties)

        # postpone the edit of content page blocks AFTER the main page's properties
        def set_content_page():
            def get_current_content_page() -> Optional[Page]:
                for block in self.reading.as_block().retrieve_children():
                    if isinstance(block.contents, ChildPageBlockContents):
                        block_title = cast(ChildPageBlockContents, block.contents).title
                        if self.name_value in block_title or block_title.strip() in [
                            "",
                            "=",
                            ">",
                        ]:
                            _content_page = Page(block.id)
                            return _content_page

            content_page_properties = PageProperties(
                {
                    TitleProperty("title"): TitleProperty.page_value.from_plain_text(
                        f">{self.title_value}"
                    )
                }
            )

            current_content_page = get_current_content_page()
            if current_content_page is None:
                content_page = self.reading.create_child_page(content_page_properties)
            elif overwrite:
                current_content_page.update(archived=True)
                content_page = self.reading.create_child_page(content_page_properties)
            else:
                content_page = current_content_page.update(content_page_properties)

            # self.reading.update(PageProperties({
            #    link_to_contents_prop:
            #        link_to_contents_prop.page_value([PageMention(content_page.id)])
            # }))
            child_contents: list[BlockContents] = [
                TableOfContentsBlockContents(BlockColor.GRAY),
                *(
                    get_block_value_of_contents_line(content_line)
                    for content_line in result.get_contents()
                ),
            ]
            length = 100
            child_contents_split_list = [
                child_contents[i : i + length]
                for i in range(0, len(child_contents), length)
            ]
            for child_contents_split in child_contents_split_list:
                content_page.as_block().append_children(child_contents_split)

        self.callables.append(set_content_page)
        return True

    def process_lib_gy(self, overwrite: bool) -> bool:
        def get_result() -> Optional[LibraryScrapResult]:
            unit = GYLibraryScraper(self.driver, self.true_name_value, "gajwa")
            if result := unit.execute():
                return result
            unit = GYLibraryScraper(self.driver, self.name_value, "gajwa")
            if result := unit.execute():
                return result
            unit = GYLibraryScraper(self.driver, self.true_name_value, "all_libs")
            if result := unit.execute():
                return result
            unit = GYLibraryScraper(self.driver, self.name_value, "all_libs")
            if result := unit.execute():
                return result

        scrap_result = get_result()
        if scrap_result is None:
            return False
        new_properties = PageProperties(
            {
                location_prop: location_prop.page_value(
                    [TextSpan(scrap_result.location_str, link=scrap_result.search_url)]
                ),
                not_available_prop: not scrap_result.available,
            }
        )
        if not overwrite:
            new_properties = self.filter_not_overwrite(new_properties)
        self.new_properties.update(new_properties)
        return True

    def filter_not_overwrite(self, new_properties: PageProperties):
        return PageProperties(
            {
                prop: prop_value
                for prop, prop_value in new_properties.items()
                if not self.reading.properties.get(prop)
            }
        )


VOLUME_KOR = re.compile(r"\d+권[.:]? ")
VOLUME_ENG = re.compile(r"VOLUME", re.IGNORECASE)

SECTION_KOR = re.compile(r"\d+부[.:]? ")
SECTION_ENG = re.compile(r"PART", re.IGNORECASE)

CHAPTER_KOR = re.compile(r"\d+장[.:]? ")
CHAPTER_ENG = re.compile(r"CHAPTER", re.IGNORECASE)

PASSAGE = re.compile(r"\d+[.:] ")


def get_block_value_of_contents_line(contents_line: str) -> BlockContents:
    rich_text = RichText(
        [TextSpan(contents_line, annotations=Annotations(color=BlockColor.GRAY))]
    )
    if VOLUME_KOR.findall(contents_line) or VOLUME_ENG.findall(contents_line):
        return Heading1BlockContents(rich_text, False)
    if SECTION_KOR.findall(contents_line) or SECTION_ENG.findall(contents_line):
        return Heading2BlockContents(rich_text, False)
    elif CHAPTER_KOR.findall(contents_line) or CHAPTER_ENG.findall(contents_line):
        return Heading3BlockContents(rich_text, False)
    return ParagraphBlockContents(rich_text)


if __name__ == "__main__":
    _action = MediaScrapAction(create_window=False)
    _action.process_pages(
        [Page("https://www.notion.so/dyhn/_-f5caa69f928b4dc1a87b76c3a4917b40?pvs=4")]
    )
