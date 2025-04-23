from __future__ import annotations

from app import backup_dir
from app.action.__core__ import CompositeAction
from app.action.match import (
    MatchActionBase,
    MatchDatei,
    MatchRecordWeekiByDatei,
    MatchRecordTimestr,
    MatchReadingStartDatei,
    CopyEventRelsToTarget,
    MatchRecordDateiByLastEditedTime,
    MatchRecordDateiByCreatedTime,
    MatchRecordDateiByTitle,
    PrependDateiOnRecordTitle,
)
from app.action.media_scrap.main import MediaScrapAction
from app.action.migration_backup import (
    MigrationBackupLoadAction,
    MigrationBackupSaveAction,
)
from app.my_block import (
    DatabaseEnum,
    schedule,
    start,
    work_needs_sch_datei_prop,
)

base = MatchActionBase()
routine_action = CompositeAction(
    [
        MigrationBackupLoadAction(backup_dir),
        MigrationBackupSaveAction(backup_dir),
        MatchDatei(base),

        MatchRecordDateiByTitle(base, DatabaseEnum.journal_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByCreatedTime(base, DatabaseEnum.journal_db, DatabaseEnum.dateid_db.title),
        PrependDateiOnRecordTitle(base, DatabaseEnum.journal_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.journal_db, DatabaseEnum.weekid_db.title,
                                DatabaseEnum.dateid_db.title),

        MatchRecordDateiByTitle(base, DatabaseEnum.event_db, DatabaseEnum.dateid_db.title, only_if_empty=True),
        MatchRecordDateiByCreatedTime(base, DatabaseEnum.event_db, DatabaseEnum.dateid_db.title, only_if_empty=True),
        PrependDateiOnRecordTitle(base, DatabaseEnum.event_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.event_db, DatabaseEnum.weekid_db.title, DatabaseEnum.dateid_db.title),
        MatchRecordTimestr(base, DatabaseEnum.event_db, DatabaseEnum.dateid_db.title),
        CopyEventRelsToTarget(base, DatabaseEnum.stage_db),
        CopyEventRelsToTarget(base, DatabaseEnum.read_db),

        MatchRecordDateiByCreatedTime(base, DatabaseEnum.extent_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.extent_db, DatabaseEnum.weekid_db.title, DatabaseEnum.dateid_db.title),

        MatchRecordDateiByTitle(base, DatabaseEnum.intent_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByCreatedTime(base, DatabaseEnum.intent_db, DatabaseEnum.dateid_db.title),
        # PrependDateiOnRecordTitle(base, DatabaseEnum.intent_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.intent_db, DatabaseEnum.weekid_db.title, DatabaseEnum.dateid_db.title),

        MatchRecordDateiByCreatedTime(base, DatabaseEnum.stage_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByTitle(base, DatabaseEnum.stage_db, schedule),
        MatchRecordDateiByCreatedTime(base, DatabaseEnum.stage_db, schedule, only_if_empty=True,
                                      only_if_this_checkbox_filled=work_needs_sch_datei_prop),
        # PrependDateiOnRecordTitle(base, DatabaseEnum.stage_db, schedule),
        MatchRecordWeekiByDatei(base, DatabaseEnum.stage_db, DatabaseEnum.weekid_db.title, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.stage_db, schedule, schedule),

        MatchRecordDateiByCreatedTime(base, DatabaseEnum.read_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByTitle(base, DatabaseEnum.read_db, schedule),
        MatchReadingStartDatei(base),
        MatchRecordWeekiByDatei(base, DatabaseEnum.read_db, DatabaseEnum.weekid_db.title,
                                DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.read_db, schedule, schedule),
        MatchRecordWeekiByDatei(base, DatabaseEnum.read_db, start, start),

        MatchRecordDateiByCreatedTime(base, DatabaseEnum.tide_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.tide_db, DatabaseEnum.weekid_db.title,
                                DatabaseEnum.dateid_db.title),

        MatchRecordDateiByCreatedTime(base, DatabaseEnum.tap_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.tap_db, DatabaseEnum.weekid_db.title,
                                DatabaseEnum.dateid_db.title),

        MatchRecordDateiByTitle(base, DatabaseEnum.genai_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByCreatedTime(base, DatabaseEnum.genai_db, DatabaseEnum.dateid_db.title),
        MatchRecordDateiByLastEditedTime(base, DatabaseEnum.genai_db, DatabaseEnum.dateid_db.title),
        PrependDateiOnRecordTitle(base, DatabaseEnum.genai_db, DatabaseEnum.dateid_db.title),
        MatchRecordWeekiByDatei(base, DatabaseEnum.genai_db, DatabaseEnum.weekid_db.title,
                                DatabaseEnum.dateid_db.title),

        MediaScrapAction(create_window=False),
    ]
)

if __name__ == "__main__":
    # import sys
    # from loguru import logger
    # logger.remove()
    # logger.add(sys.stderr, level="TRACE")
    # from datetime import timedelta
    # routine_action.run_recent(interval=timedelta(minutes=5))
    # routine_action.run_by_last_edited_time(datetime(2024, 1, 7, 17, 0, 0, tzinfo=my_tz), None)
    routine_action.run_from_last_success(update_last_success_time=False)
