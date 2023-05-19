from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

from selenium.common.exceptions import NoSuchElementException, UnexpectedAlertPresentException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from notion_df.util.collection import StrEnum

SelectLib_T = Literal['all_libs', 'gajwa']


@dataclass
class LibraryScrapResult:
    lib_name: str
    priority: int
    book_code: str
    availability: bool

    @classmethod
    def gajwa(cls, book_code: str, availability: bool) -> LibraryScrapResult:
        return cls('가좌도서관', 1, book_code, availability)

    @classmethod
    def gy_all_libs(cls, book_code: str, availability: bool) -> LibraryScrapResult:
        return cls('고양시 상호대차', -1, book_code, availability)

    def __str__(self):
        return " ".join(val for val in [self.lib_name, self.book_code, self.availability_str] if val)

    @property
    def availability_str(self) -> str:
        return '가능' if self.availability else '불가능'


class GoyangLibraryScraper:
    def __init__(self, driver: WebDriver):
        self.driver = driver
        self._driver_active = False
        self.driver.start_client()

    def process_page(self, title: str) -> Optional[LibraryScrapResult]:
        if not self._driver_active:
            self.driver.start_client()
            self._driver_active = True

        query = GoyangLibraryQueryMaker(self.driver, title, 'gajwa')
        query.execute()
        if gajwa_option := query.result:
            return gajwa_option
        query = GoyangLibraryQueryMaker(self.driver, title, 'all_libs')
        query.execute()
        if gy_all_libs_option := query.result:
            gy_all_libs_option.lib_name = '고양시 상호대차'
            gy_all_libs_option.book_code = ''
            gy_all_libs_option.priority = -1
            return gy_all_libs_option
        return


class CSSTag(StrEnum):
    input_box = '#searchKeyword'
    search_button = '#searchBtn'
    all_libs = '#searchLibraryAll'
    gajwa = '#searchManageCodeArr2'


class GoyangLibraryQueryMaker:
    def __init__(self, driver: WebDriver, title: str, select_lib: SelectLib_T):
        self.driver = driver
        # self.driver.minimize_window()
        self.select_lib = select_lib
        self.title = title
        self.now_page_num = 1
        self.result: Optional[LibraryScrapResult] = None

    def find_element(self, css_tag: CSSTag):
        return self.driver.find_element(By.CSS_SELECTOR, css_tag)

    def click_element(self, css_tag: CSSTag):
        self.driver.execute_script(f'document.querySelector("{css_tag}").click();')

    def remove_element(self, css_tag: CSSTag):
        self.driver.execute_script(f"""
var l = document.querySelector("{css_tag}");
l.parentNode.removeChild(l);
        """)

    def execute(self):
        # load main page
        url_main_page = 'https://www.goyanglib.or.kr/center/menu/10003/program/30001/searchSimple.do'
        self.driver.get(url_main_page)

        # insert title
        input_box = self.find_element(CSSTag.input_box)
        input_box.send_keys(self.title)

        match self.select_lib:
            case 'all_libs':
                self.click_element(CSSTag.all_libs)
            case 'gajwa':
                self.click_element(CSSTag.all_libs)
                self.click_element(CSSTag.gajwa)

        self.find_element(CSSTag.search_button).click()
        self.driver.implicitly_wait(3)

        # if no result
        try:
            if self.driver.find_elements(By.CLASS_NAME, "noResultNote"):
                return
        except UnexpectedAlertPresentException:
            wait = WebDriverWait(self.driver, 10)
            alert = wait.until(expected_conditions.alert_is_present())
            alert.accept()

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
        tag = f'#bookList > div.pagingWrap > p > a:nth-child({child_num})'
        try:
            page_button = self.driver.find_element(By.CSS_SELECTOR, tag)
        except NoSuchElementException:
            return False
        page_button.click()
        self.now_page_num = num
        return True

    def move_to_next_page_section(self):
        tag = '#bookList > div.pagingWrap > p > a.btn-paging.next'
        try:
            next_page_section_button = self.driver.find_element(By.CSS_SELECTOR, tag)
        except NoSuchElementException:
            return False
        next_page_section_button.click()
        return True

    def evaluate_page(self):
        tag = '#bookList > div.bookList.listViewStyle > ul > li > div.bookArea'
        book_areas = self.driver.find_elements(By.CSS_SELECTOR, tag)
        for book_area in book_areas:
            if self.evaluate_book_area(book_area):
                return True
        return False

    def evaluate_book_area(self, book_area: WebElement):
        parser = GoyangLibraryScrapBookAreaParser(book_area)
        # if parser.check_title():
        book_code = parser.get_book_code()
        availability = parser.get_availability()
        del parser
        if self.select_lib == 'gajwa':
            self.result = LibraryScrapResult.gajwa(book_code, availability)
            return True
        elif self.select_lib == 'all_libs':
            # if all_libs, should proceed until element with availability=True arises.
            self.result = LibraryScrapResult.gy_all_libs(book_code, availability)
            return True
        return False


class GoyangLibraryScrapBookAreaParser:
    def __init__(self, book_area: WebElement):
        self.book_area = book_area

    def get_book_code(self):
        tag = 'div.bookData > div > div > p.kor.on > span:nth-child(3)'
        try:
            element = self.book_area.find_element(By.CSS_SELECTOR, tag)
            return element.text
        except NoSuchElementException as e:
            print(f"{type(e).__name__}: {e.msg}")
            return ''

    def get_availability(self):
        tag = 'div.bookData > div > ul > li.title > span > strong'
        try:
            element = self.book_area.find_element(By.CSS_SELECTOR, tag)
            return "대출가능" in element.text
        except NoSuchElementException as e:
            print(f"{type(e).__name__}: {e.msg}")
            return ''

    # def check_title(self):
    #     tag = 'div.bookData > div.book_dataInner > div.book_name > p.kor.on > a'
    #     element = self.book_area.find_element(By.CSS_SELECTOR, tag)
    #     book_title = element.get_attribute('title')
    #     return True
