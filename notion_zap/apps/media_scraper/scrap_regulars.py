from typing import Optional

from notion_zap.cli import editors
from notion_zap.cli.utility import stopwatch
from notion_zap.apps.media_scraper.structs.controller_base_logic import (
    ReadingDBController, ReadingPageWriter)
from notion_zap.apps.media_scraper.module_bkst.main import BookstoreDataWriter
from notion_zap.apps.media_scraper.module_lib import LibraryManager


class RegularScrapController(ReadingDBController):
    TASKS_BKST = {'bookstore'}
    TASKS_LIBS = {'gy_lib', 'snu_lib'}
    BKST = BookstoreDataWriter

    def __init__(self, tasks: Optional[set] = None, title=''):
        super().__init__()
        if not tasks:
            tasks = self.TASKS_BKST | self.TASKS_LIBS
        self.global_tasks = tasks
        self.title = title
        self.lib = LibraryManager(self.global_tasks)
        self.has_lib_tasks = any(lib in self.global_tasks for lib in self.TASKS_LIBS)

    def execute(self, request_size=0):
        if not self.fetch(request_size):
            return
        if self.has_lib_tasks:
            self.lib.start()
        for page in self.pagelist:
            self.edit(page)
        if self.has_lib_tasks:
            self.lib.quit()

    def fetch(self, request_size):
        query = self.pagelist.open_query()
        maker = query.filter_maker
        ft = query.open_filter()

        frame = maker.checkbox_at('is_book')
        ft &= frame.is_not_empty()

        frame = maker.select_at('edit_status')
        ft &= (
                frame.equals_to_any(frame.prop_value_groups['regular_scraps'])
                | frame.is_empty()
        )

        if self.title:
            frame = maker.text_at('title')
            ft_title = frame.starts_with(self.title)
            ft &= ft_title
        query.push_filter(ft)
        pages = query.execute(request_size, print_heads=5)
        return pages

    def edit(self, page: editors.PageRow):
        status = ReadingPageStatusWriter(page, self.global_tasks.copy())
        if status.tasks:
            stopwatch(f'개시: {page.title}')
            if 'bookstore' in status.tasks:
                self.BKST(status).execute()
            if any(lib_str in status.tasks for lib_str in ['snu_lib', 'gy_lib']):
                self.lib.execute(status, status.tasks)
            status.set_complete_flag()
            page.save()
        else:
            stopwatch(f'무시: {page.title}')
            return


class ReadingPageStatusWriter(ReadingPageWriter):
    def __init__(self, page: editors.PageRow, tasks: set):
        super().__init__(page)
        self.tasks = tasks
        if self._initial_status == 'continue':
            self.tasks.remove('bookstore')


if __name__ == '__main__':
    RegularScrapController().execute(request_size=5)
