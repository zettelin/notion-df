from typing import Union

from .lib_gy import GoyangLibrary
from .lib_snu import SNULibrary
from notion_py.interface import TypeName
from notion_py.interface.utility import stopwatch


class LibraryScraper:
    def __init__(self, handler):
        self.handler = handler
        self.page: TypeName.tabular_page = handler.page
        self.props = self.page.props
        self.targets = handler.targets
        self.gylib = GoyangLibrary() if 'gy_lib' in self.targets else None
        self.snulib = SNULibrary() if 'snu_lib' in self.targets else None
        self.datas = {}

    def execute(self):
        self.scrap()
        self.set_lib_datas()

    def scrap(self):
        book_names = self.handler.get_names()
        if 'snu_lib' in self.handler.targets:
            # noinspection PyTypeChecker
            snu_lib = self.snulib.execute(book_names)
            if snu_lib:
                stopwatch(f'서울대: {snu_lib}')
                self.datas.update(snu=snu_lib)
        if 'gy_lib' in self.handler.targets:
            # noinspection PyTypeChecker
            gy_lib = self.gylib.execute(book_names)
            if gy_lib:
                stopwatch(f"고양시: {gy_lib['lib_name']}  {gy_lib['book_code']}")
                self.datas.update(gy=gy_lib)

    def set_lib_datas(self):
        datastrings = []
        if 'gy' in self.datas.keys() and \
                self.datas['gy']['lib_name'] == GoyangLibrary.str_gajwa_lib:
            first_lib = 'gy'
        elif 'snu' in self.datas.keys():
            first_lib = 'snu'
        elif 'gy' in self.datas.keys():
            first_lib = 'gy'
        else:
            self.handler.status = self.handler.status_enum['lib_missing']
            return

        first_data = self.datas.pop(first_lib)
        string, available = self.format_lib(first_lib, first_data)
        datastrings.append(string)
        datastrings.extend([self.format_lib(lib, data)[0]
                            for lib, data in self.datas.items()])
        joined_string = '; '.join(datastrings)

        self.props.set_overwrite_option(True)
        self.props.write_text_at('location', joined_string)
        self.props.write_checkbox_at('not_available', not available)

    @staticmethod
    def format_lib(lib: str, res: Union[dict, str]) -> tuple[str, bool]:
        if lib == 'gy':
            string = f"{res['lib_name']}"
            if book_code := res['book_code']:
                string += f" {book_code}"
            available = res['available']
            return string, available
        elif lib == 'snu':
            return res, True
        else:
            return res, True
