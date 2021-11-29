from notion_zap.cli.utility import stopwatch
from notion_zap.apps.prop_matcher.regulars import RegularMatchController
from notion_zap.apps.media_scraper import RegularScrapController


def execute():
    RegularMatchController().execute()
    RegularScrapController().execute(request_size=5)

    stopwatch('모든 작업 완료')
