from __future__ import annotations

from workflow import backup_dir
from workflow.action.media_scraper import MediaScraper
from workflow.action.migration_backup import MigrationBackupLoadAction, MigrationBackupSaveAction
from workflow.action.prop_matcher import MatchActionBase, MatchWeekByDateValue, MatchDateByCreatedTime, \
    MatchWeekByRefDate, MatchTimestr, MatchReadingsStartDate, MatchEventProgress
from workflow.block_enum import DatabaseEnum
from workflow.core.action import Action, CompositeAction


def get_action() -> Action:
    base = MatchActionBase()
    return CompositeAction([
        MigrationBackupLoadAction(backup_dir),
        MigrationBackupSaveAction(backup_dir),

        MatchWeekByDateValue(base),

        MatchDateByCreatedTime(base, DatabaseEnum.event_db, '일간', read_title=True, write_title=True),
        MatchDateByCreatedTime(base, DatabaseEnum.event_db, '정리'),
        MatchWeekByRefDate(base, DatabaseEnum.event_db, '주간', '일간'),
        MatchTimestr(base, DatabaseEnum.event_db, '일간'),
        MatchEventProgress(base),
        MatchDateByCreatedTime(base, DatabaseEnum.schedule_db, '정리'),

        MatchDateByCreatedTime(base, DatabaseEnum.stage_db, '일간', read_title=True, write_title=True),
        MatchWeekByRefDate(base, DatabaseEnum.stage_db, '주간', '일간'),
        MatchDateByCreatedTime(base, DatabaseEnum.point_db, '일간'),
        MatchWeekByRefDate(base, DatabaseEnum.event_db, '주간', '일간'),

        MatchDateByCreatedTime(base, DatabaseEnum.issue_db, '생성'),
        MatchWeekByRefDate(base, DatabaseEnum.issue_db, '주간', '일간'),
        MatchReadingsStartDate(base),
        MatchDateByCreatedTime(base, DatabaseEnum.reading_db, '생성'),
        MatchWeekByRefDate(base, DatabaseEnum.reading_db, '주간', '일간'),
        MatchWeekByRefDate(base, DatabaseEnum.reading_db, '시작', '시작'),  # TODO: can be deprecated

        MatchWeekByRefDate(base, DatabaseEnum.topic_db, '주간', '일간'),
        MatchDateByCreatedTime(base, DatabaseEnum.gist_db, '일간'),
        MatchWeekByRefDate(base, DatabaseEnum.gist_db, '주간', '일간'),

        MatchDateByCreatedTime(base, DatabaseEnum.schedule_db, '정리'),
        MatchWeekByRefDate(base, DatabaseEnum.schedule_db, '주간', '일간'),
        MatchDateByCreatedTime(base, DatabaseEnum.point_db, '일간'),
        MatchWeekByRefDate(base, DatabaseEnum.point_db, '주간', '일간'),

        MediaScraper(create_window=False),

        # DeprMatchTopic(base, DatabaseEnum.event_db, DatabaseEnum.issue_db, DatabaseEnum.issue_db.prefix_title,
        #            DatabaseEnum.topic_db.prefix_title, DatabaseEnum.topic_db.prefix_title),
        # DeprMatchTopic(base, DatabaseEnum.event_db, DatabaseEnum.event_db, DatabaseEnum.event_db.prefix_title,
        #            DatabaseEnum.topic_db.prefix_title, DatabaseEnum.topic_db.prefix_title),
        # DeprMatchTopic(base, DatabaseEnum.event_db, DatabaseEnum.reading_db, DatabaseEnum.reading_db.prefix_title,
        #            DatabaseEnum.topic_db.prefix_title, DatabaseEnum.topic_db.prefix_title),
        # DeprMatchTopic(base, DatabaseEnum.schedule_db, DatabaseEnum.issue_db, DatabaseEnum.issue_db.prefix_title,
        #                DatabaseEnum.topic_db.prefix_title, DatabaseEnum.topic_db.prefix_title),
        # DeprMatchTopic(base, DatabaseEnum.schedule_db, DatabaseEnum.reading_db,
        #                DatabaseEnum.reading_db.prefix_title,
        #                DatabaseEnum.topic_db.prefix_title, DatabaseEnum.topic_db.prefix_title),
        # MatchDateByCreatedTime(base, DatabaseEnum.depr_event_db, '일간'),
        # MatchDateByCreatedTime(base, DatabaseEnum.depr_event_db, '생성'),
        # MatchWeekByRefDate(base, DatabaseEnum.depr_event_db, '주간', '일간'),
        # MatchTimestr(base, DatabaseEnum.depr_event_db, '일간'),
        # MatchDateByCreatedTime(base, DatabaseEnum.depr_subject_db, '일간'),
        # MatchWeekByRefDate(base, DatabaseEnum.depr_subject_db, '주간', '일간'),
    ])


if __name__ == '__main__':
    # get_action().run_by_last_edited_time(datetime(2024, 1, 7, 17, 0, 0, tzinfo=my_tz), None)
    # get_action().run_recent(interval=timedelta(hours=24))
    get_action().run_from_last_success(update_last_success_time=True)
