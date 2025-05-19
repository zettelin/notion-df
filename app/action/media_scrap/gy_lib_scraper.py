from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from app import out_dir
from app.service.webdriver_service import WebDriverService
from notion_df.core.collection import StrEnum

LibKey = Literal["all_libs", "gajwa"]


@dataclass
class LibraryScrapResult:
    lib_key: LibKey
    lib_name: str
    priority: int
    book_code: str
    available: bool
    search_url: str = None

    @classmethod
    def gajwa(cls, book_code: str, availability: bool) -> LibraryScrapResult:
        return cls("gajwa", "가좌도서관", 1, book_code, availability)

    @classmethod
    def gy_all_libs(cls, book_code: str, availability: bool) -> LibraryScrapResult:
        return cls("all_libs", "고양시 상호대차", -1, book_code, availability)

    @property
    def location_str(self) -> str:
        if self.lib_key == "gajwa":
            vals = [self.lib_name, self.book_code, self.availability_str]
        else:
            vals = [self.lib_name, self.availability_str]
        return " ".join(val for val in vals if val)

    @property
    def availability_str(self) -> str:
        return "가능" if self.available else "불가능"


class GYLibraryCSSTag(StrEnum):
    input_box = "#searchKeyword"
    search_button = "#searchBtn"
    all_libs = "#searchLibraryAll"
    gajwa = "#searchManageCodeArr2"


class GYLibraryScraper:
    driver: WebDriver

    def __init__(self, driver: WebDriver, title: str, lib_key: LibKey):
        self.driver = driver
        self.driver.implicitly_wait(10)
        self.driver.set_window_size(1920, 1080)
        self.driver_wait = WebDriverWait(self.driver, 120)
        self.lib_key = lib_key
        self.title = title
        self.now_page_num = 1
        self.result: Optional[LibraryScrapResult] = None

    def find_element(self, css_tag: GYLibraryCSSTag):
        return self.driver.find_element(By.CSS_SELECTOR, css_tag)

    def send_keys(self, css_tag: GYLibraryCSSTag, value: str):
        element = self.find_element(css_tag)
        self.driver.execute_script("arguments[0].value = arguments[1]", element, value)

    def click_element(self, css_tag: GYLibraryCSSTag):
        # self.driver_wait.until(
        #    EC.element_to_be_clickable((By.CSS_SELECTOR, css_tag)))
        element = self.find_element(css_tag)
        self.driver.execute_script("arguments[0].click();", element)

    def remove_element(self, css_tag: GYLibraryCSSTag):
        self.driver.execute_script(f"""
var l = document.querySelector("{css_tag}");
l.parentNode.removeChild(l);
        """)

    def execute(self) -> Optional[LibraryScrapResult]:
        if not self.title:
            return
        # load main page
        url_main_page = "https://www.goyanglib.or.kr/center/menu/10003/program/30001/searchSimple.do"
        self.driver.get(url_main_page)

        # insert title
        self.driver_wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, GYLibraryCSSTag.input_box))
        )

        (out_dir / "page_source.html").write_text(self.driver.page_source)
        self.send_keys(GYLibraryCSSTag.input_box, self.title)

        match self.lib_key:
            case "all_libs":
                pass
            case "gajwa":
                self.click_element(GYLibraryCSSTag.all_libs)
                self.click_element(GYLibraryCSSTag.gajwa)

        self.click_element(GYLibraryCSSTag.search_button)
        if self.driver.find_elements(By.CLASS_NAME, "noResultNote"):
            return

        search_url = self.driver.current_url
        self.examine_result()
        self.result.search_url = search_url
        return self.result

    def examine_result(self):
        proceed = True
        while proceed:
            if self.evaluate_page_section():
                return
            proceed = self.move_to_next_page_section()

    def evaluate_page_section(self):
        for num in range(1, 10 + 1):
            if not self.move_page(num):
                return False
            if self.evaluate_page():
                return True

    def move_page(self, num: int):
        assert 1 <= num <= 10
        if num == self.now_page_num:
            return True
        if num > self.now_page_num:
            child_num = num + 1
        else:
            child_num = num + 2
        tag = f"#bookList > div.pagingWrap > p > a:nth-child({child_num})"
        try:
            page_button = self.driver.find_element(By.CSS_SELECTOR, tag)
        except NoSuchElementException:
            return False
        page_button.click()
        self.now_page_num = num
        return True

    def move_to_next_page_section(self):
        tag = "#bookList > div.pagingWrap > p > a.btn-paging.next"
        try:
            next_page_section_button = self.driver.find_element(By.CSS_SELECTOR, tag)
        except NoSuchElementException:
            return False
        next_page_section_button.click()
        return True

    def evaluate_page(self):
        tag = "#bookList > div.bookList.listViewStyle > ul > li > div.bookArea"
        book_areas = self.driver.find_elements(By.CSS_SELECTOR, tag)
        for book_area in book_areas:
            self.result = GoyangLibraryScrapBookAreaParser(
                book_area, self.lib_key
            ).result
            if self.lib_key == "gajwa" or (
                self.lib_key == "all_libs" and self.result.available
            ):
                return True
        return False


class GoyangLibraryScrapBookAreaParser:
    def __init__(self, book_area: WebElement, lib_key: LibKey):
        self.book_area = book_area
        self.lib_key = lib_key
        if self.lib_key == "gajwa":
            self.result = LibraryScrapResult.gajwa(
                self.get_book_code(), self.get_availability()
            )
        elif self.lib_key == "all_libs":
            # if all_libs, should proceed until element with availability=True arises.
            self.result = LibraryScrapResult.gy_all_libs(
                self.get_book_code(), self.get_availability()
            )

    def get_book_code(self):
        tag = "div.bookData > div > div > p.kor.on > span:nth-child(3)"
        try:
            element = self.book_area.find_element(By.CSS_SELECTOR, tag)
            return element.text
        except NoSuchElementException as e:
            print(f"{type(e).__name__}: {e.msg}")
            return ""

    def get_availability(self):
        tag = "div.bookData > div > ul > li.title > span > strong"
        try:
            element = self.book_area.find_element(By.CSS_SELECTOR, tag)
            return "대출가능" in element.text
        except NoSuchElementException as e:
            print(f"{type(e).__name__}: {e.msg}")
            return ""

    # def check_title(self):
    #     tag = 'div.bookData > div.book_dataInner > div.book_name > p.kor.on > a'
    #     element = self.book_area.find_element(By.CSS_SELECTOR, tag)
    #     book_title = element.get_attribute('title')
    #     return True


if __name__ == "__main__":
    my_title = "하나부터 열까지 신경 쓸 게 너무 많은 브랜딩"
    with WebDriverService(create_window=False).create() as _driver:
        try:
            gy = GYLibraryScraper(_driver, my_title, "gajwa")
            print(gy.execute())
            gy = GYLibraryScraper(_driver, my_title, "all_libs")
            print(gy.execute())
        except Exception as e:
            raise Exception(_driver.save_screenshot("/home/ubuntu/screenshot.png"), e)
