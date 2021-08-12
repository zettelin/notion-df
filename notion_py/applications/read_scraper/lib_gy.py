from __future__ import annotations
from typing import Callable, Optional, Any
import os
import emoji
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException, NoSuchWindowException

from notion_py.utility import stopwatch

tag_input_box = '#a_q'
tag_search_button = '#sb1 > a'
tag_page_buttons = '#pagelist > ul > li > a'
tag_lib_names = '#lists > ul > li > dl > dd:nth-child(3)'
tags_availability = '#lists > ul > li:nth-child({}) > dl > dd:nth-child(4)'
tag_book_code = '#printArea > div.tblType01.mt30 > table > tbody > tr:nth-child(2) > td:nth-child(2)'
tags_detail_info_button = '#lists > ul > li:nth-child({}) > dl > dt > a'


def retry_webdriver(method: Callable, recursion_limit=5) -> Callable:
    def wrapper(self, *args, recursion=0):
        if recursion != 0:
            stopwatch(f'selenium 재시작 {recursion}/{recursion_limit}회')
        try:
            response = method(self, *args)
        except (NoSuchElementException, StaleElementReferenceException):
            if recursion == recursion_limit:
                return None
            # driver.stop_client()
            # driver.start_client()
            response = wrapper(self, recursion=recursion + 1)
        return response
    return wrapper


def try_twice(function: Callable[[Any, str], Any]):
    def wrapper(self, strings: tuple[str, str]):
        first_str, second_str = strings
        has_true_name = second_str and (second_str != first_str)
        result = function(self, first_str)
        if not result and has_true_name:
            result = function(self, second_str)
        return result
    return wrapper


def remove_emoji(text):
    return emoji.get_emoji_regexp().sub(u'', text)


class SeleniumScraper:
    driver_num = 1

    def __init__(self):
        self.drivers = []
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        for i in range(self.driver_num):
            driver = webdriver.Chrome(self.chromedriver_path, options=options,
                                      service_log_path=os.devnull)
            driver.minimize_window()
            driver.start_client()
            self.drivers.append(driver)

    @property
    def chromedriver_path(self):
        # print(os.path.abspath('chromedriver.exe'))
        return os.path.abspath('chromedriver.exe')

    def quit(self):
        for driver in self.drivers:
            driver.quit()

    def __del__(self):
        self.quit()


class GoyangLibrary(SeleniumScraper):
    driver_num = 2
    str_gajwa_lib = '가좌도서관'
    str_other_lib = '고양시 상호대차'

    @try_twice
    @retry_webdriver
    def execute(self, book_name: str) -> Optional[dict]:
        book_name = remove_emoji(book_name)
        """
        :return: [도서관 이름: str('가좌도서관', '고양시 상호대차', '스크랩 실패'),
                    현재 대출 가능: bool,
                    서지번호: str('가좌도서관'일 경우에만 non-empty)]
        """
        url_main_page = 'https://www.goyanglib.or.kr/center/data/search.asp'

        driver = self.drivers[0]
        try:
            driver.get(url_main_page)
            driver.implicitly_wait(3)
            input_box = driver.find_element_by_css_selector(tag_input_box)
        except NoSuchWindowException:
            return None
        input_box.send_keys(book_name)

        search_button = self.drivers[0].find_element_by_css_selector(tag_search_button)
        search_button.click()

        self.drivers[0].implicitly_wait(3)
        no_book = self.drivers[0].find_elements_by_css_selector('#lists > ul > li')
        if no_book and '검색하신 도서가 없습니다' in no_book[0].text:
            return None

        self.drivers[0].implicitly_wait(10)
        page_buttons = self.drivers[0].find_elements_by_css_selector(tag_page_buttons)
        page_buttons = page_buttons[1:-1]
        pages = len(page_buttons)

        available_somewhere = False
        for now_page in range(pages):
            if now_page != 0:
                try:
                    page_buttons[now_page].click()
                    self.drivers[0].implicitly_wait(5)
                except StaleElementReferenceException:
                    break

            lib_names = self.drivers[0].find_elements_by_css_selector(tag_lib_names)
            if not lib_names:
                break

            for lib_index, lib_name_raw in enumerate(lib_names):
                # self.drivers[0].find_element_by_css_selector(tag_availability).text = '대출(가능), 예약(불가능) \n ..'
                # 여기서 split(',')[0] 하면 쉼표 전에서 자를 수 있다.
                tag_availability = tags_availability.format(str(lib_index + 1))
                available_here_str = self.drivers[0].find_element_by_css_selector(tag_availability).text.split(',')[0]
                available_here = not ('불가능' in available_here_str)

                if '가좌' in lib_name_raw.text:
                    tag_detail_info_button = tags_detail_info_button.format(str(lib_index + 1))
                    detail_button = self.drivers[0].find_element_by_css_selector(tag_detail_info_button)
                    detail_button_url = detail_button.get_attribute('href')
                    book_code = ''
                    try:
                        driver.get(detail_button_url)
                        driver.implicitly_wait(3)
                        book_code = driver.find_element_by_css_selector(tag_book_code).text
                    except NoSuchElementException:
                        pass
                    return {
                        'lib_name': self.str_gajwa_lib,
                        'available': available_here,
                        'book_code': book_code
                    }
                else:
                    available_somewhere = available_here or available_somewhere

        if available_somewhere:
            return {
                'lib_name': self.str_other_lib,
                'available': True,
                'book_code': ''
            }
        else:
            return None
