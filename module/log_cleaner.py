import os
import re
import shutil
import threading
import time
from datetime import datetime, timedelta

from module.logger import logger


LOG_DIR = "./log"
LOG_ERROR_DIR = "./log/error"
DEFAULT_SCHEDULED_TIME = "00:00"
DEFAULT_KEEP_DAYS = 7
MIN_KEEP_DAYS = 1
MAX_KEEP_DAYS = 365

# Matches ./log/YYYY-MM-DD_*.txt
_LOG_FILE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})_.+\.txt$")
# Matches a pure integer directory name (millisecond timestamp)
_MS_TIMESTAMP_PATTERN = re.compile(r"^\d+$")


def validate_scheduled_time(value):
    """
    Validate and normalize a HH:MM time string.

    Args:
        value (str):

    Returns:
        str: Normalized 'HH:MM' string, or DEFAULT_SCHEDULED_TIME if invalid.
    """
    if not isinstance(value, str):
        logger.warning(
            f'LogCleaner: ScheduledTime "{value}" is not a string, reset to {DEFAULT_SCHEDULED_TIME}'
        )
        return DEFAULT_SCHEDULED_TIME
    value = value.strip()
    if not re.match(r"^\d{2}:\d{2}$", value):
        logger.warning(
            f'LogCleaner: ScheduledTime "{value}" is not in HH:MM format, reset to {DEFAULT_SCHEDULED_TIME}'
        )
        return DEFAULT_SCHEDULED_TIME
    hour, minute = value.split(":")
    hour, minute = int(hour), int(minute)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        logger.warning(
            f'LogCleaner: ScheduledTime "{value}" is out of valid range, reset to {DEFAULT_SCHEDULED_TIME}'
        )
        return DEFAULT_SCHEDULED_TIME
    return f"{hour:02d}:{minute:02d}"


def validate_keep_days(value):
    """
    Validate keep_days value. Must be an integer between MIN_KEEP_DAYS and MAX_KEEP_DAYS.

    Args:
        value (int, str):

    Returns:
        int: Valid keep_days, or DEFAULT_KEEP_DAYS if invalid.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        logger.warning(
            f'LogCleaner: KeepDays "{value}" is not an integer, reset to {DEFAULT_KEEP_DAYS}'
        )
        return DEFAULT_KEEP_DAYS
    if not (MIN_KEEP_DAYS <= value <= MAX_KEEP_DAYS):
        logger.warning(
            f"LogCleaner: KeepDays {value} is out of range [{MIN_KEEP_DAYS}, {MAX_KEEP_DAYS}], "
            f"reset to {DEFAULT_KEEP_DAYS}"
        )
        return DEFAULT_KEEP_DAYS
    return value


class LogCleaner:
    def __init__(self, config):
        """
        Args:
            config: AzurLaneConfig instance
        """
        self.config = config
        self._scheduler_thread = None
        self._stop_event = threading.Event()

    def _get_validated_keep_days(self):
        """
        Returns:
            int:
        """
        keep_days = validate_keep_days(self.config.LogCleaner_KeepDays)
        if keep_days != self.config.LogCleaner_KeepDays:
            self.config.LogCleaner_KeepDays = keep_days
        return keep_days

    def _get_validated_scheduled_time(self):
        """
        Returns:
            str: HH:MM
        """
        scheduled_time = validate_scheduled_time(self.config.LogCleaner_ScheduledTime)
        if scheduled_time != self.config.LogCleaner_ScheduledTime:
            self.config.LogCleaner_ScheduledTime = scheduled_time
        return scheduled_time

    @staticmethod
    def _cutoff_timestamp_ms(cutoff_date):
        """
        Convert a date to a millisecond timestamp (start of that day).

        Args:
            cutoff_date (datetime.date):

        Returns:
            int: Millisecond timestamp
        """
        return int(
            datetime(cutoff_date.year, cutoff_date.month, cutoff_date.day).timestamp()
            * 1000
        )

    def _clean_log_files(self, cutoff_date):
        """
        Delete ./log/YYYY-MM-DD_*.txt files whose date is before cutoff_date.

        Args:
            cutoff_date (datetime.date):

        Returns:
            tuple[int, int]: (deleted, skipped)
        """
        deleted = 0
        skipped = 0
        if not os.path.isdir(LOG_DIR):
            return deleted, skipped
        for filename in os.listdir(LOG_DIR):
            filepath = os.path.join(LOG_DIR, filename)
            if not os.path.isfile(filepath):
                continue
            match = _LOG_FILE_PATTERN.match(filename)
            if not match:
                continue
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date < cutoff_date:
                try:
                    os.remove(filepath)
                    logger.info(f"Deleted log: {filename}")
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete log {filename}: {e}")
            else:
                skipped += 1
        return deleted, skipped

    def _clean_error_dirs(self, cutoff_ms):
        """
        Delete ./log/error/<timestamp_ms>/ subdirectories whose timestamp is before cutoff_ms.

        Args:
            cutoff_ms (int): Millisecond timestamp cutoff

        Returns:
            tuple[int, int]: (deleted, skipped)
        """
        deleted = 0
        skipped = 0
        if not os.path.isdir(LOG_ERROR_DIR):
            return deleted, skipped
        for dirname in os.listdir(LOG_ERROR_DIR):
            dirpath = os.path.join(LOG_ERROR_DIR, dirname)
            if not os.path.isdir(dirpath):
                continue
            if not _MS_TIMESTAMP_PATTERN.match(dirname):
                continue
            ts = int(dirname)
            if ts < cutoff_ms:
                try:
                    shutil.rmtree(dirpath)
                    logger.info(f"Deleted error dir: {dirname}")
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete error dir {dirname}: {e}")
            else:
                skipped += 1
        return deleted, skipped

    def _clean_screenshots(self, cutoff_ms):
        """
        Delete screenshot files under the configured SaveFolder whose filename
        (without extension) is a millisecond timestamp older than cutoff_ms.
        After deleting files, remove any empty subdirectories.

        Args:
            cutoff_ms (int): Millisecond timestamp cutoff

        Returns:
            tuple[int, int]: (deleted_files, skipped_files)
        """
        deleted = 0
        skipped = 0
        screenshot_dir = self.config.DropRecord_SaveFolder
        if not screenshot_dir or not os.path.isdir(screenshot_dir):
            return deleted, skipped

        # Walk subdirectories; screenshots are stored as
        # <SaveFolder>/<category>/<timestamp_ms>.<ext>
        for root, dirs, files in os.walk(screenshot_dir, topdown=False):
            for filename in files:
                name_no_ext = os.path.splitext(filename)[0]
                if not _MS_TIMESTAMP_PATTERN.match(name_no_ext):
                    continue
                ts = int(name_no_ext)
                filepath = os.path.join(root, filename)
                if ts < cutoff_ms:
                    try:
                        os.remove(filepath)
                        logger.info(
                            f"Deleted screenshot: {os.path.relpath(filepath, screenshot_dir)}"
                        )
                        deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete screenshot {filepath}: {e}")
                else:
                    skipped += 1

            # Remove empty subdirectories (but not the root SaveFolder itself)
            if root != screenshot_dir and not os.listdir(root):
                try:
                    os.rmdir(root)
                    logger.info(
                        f"Removed empty dir: {os.path.relpath(root, screenshot_dir)}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to remove empty dir {root}: {e}")

        return deleted, skipped

    def clean_logs(self, keep_days=None):
        """
        Clean all expired log files, error snapshot directories, and screenshot files.

        - ./log/YYYY-MM-DD_*.txt           judged by date in filename
        - ./log/error/<timestamp_ms>/      judged by millisecond timestamp in dirname
        - <SaveFolder>/<category>/<ts>.*   judged by millisecond timestamp in filename

        Args:
            keep_days (int, optional): Number of days to keep. Uses config value if None.
        """
        if keep_days is None:
            keep_days = self._get_validated_keep_days()

        cutoff_date = datetime.now().date() - timedelta(days=keep_days)
        cutoff_ms = self._cutoff_timestamp_ms(cutoff_date)

        logger.hr("Log Cleaner", level=2)
        logger.info(
            f"Cleaning files older than {cutoff_date} (keeping {keep_days} days)"
        )

        log_del, log_kept = self._clean_log_files(cutoff_date)
        err_del, err_kept = self._clean_error_dirs(cutoff_ms)
        ss_del, ss_kept = self._clean_screenshots(cutoff_ms)

        logger.info(
            f"Log clean finished: "
            f"logs {log_del} deleted / {log_kept} kept, "
            f"error dirs {err_del} deleted / {err_kept} kept, "
            f"screenshots {ss_del} deleted / {ss_kept} kept"
        )

    def run_on_startup(self):
        """
        Run log cleaning on startup if configured.
        """
        if not self.config.LogCleaner_Enable:
            return
        if not self.config.LogCleaner_CleanOnStartup:
            return
        logger.info("LogCleaner: Running startup clean")
        self.clean_logs()

    def _seconds_until_next_run(self, scheduled_time):
        """
        Calculate seconds until the next scheduled run time.

        Args:
            scheduled_time (str): HH:MM format

        Returns:
            float: Seconds until next run
        """
        hour, minute = [int(x) for x in scheduled_time.split(":")]
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return (next_run - now).total_seconds()

    def _scheduler_loop(self):
        """
        Background thread loop for scheduled log cleaning.
        """
        logger.info("LogCleaner: Scheduler thread started")
        while not self._stop_event.is_set():
            # Re-read config every cycle to pick up changes
            if (
                not self.config.LogCleaner_Enable
                or not self.config.LogCleaner_ScheduledClean
            ):
                logger.info(
                    "LogCleaner: Scheduled clean disabled, scheduler thread exiting"
                )
                break

            scheduled_time = self._get_validated_scheduled_time()
            wait_seconds = self._seconds_until_next_run(scheduled_time)
            logger.info(
                f"LogCleaner: Next scheduled clean at {scheduled_time}, waiting {wait_seconds:.0f}s"
            )

            # Wait in 60-second intervals to allow stop detection
            waited = 0
            while waited < wait_seconds:
                if self._stop_event.is_set():
                    break
                sleep_time = min(60, wait_seconds - waited)
                time.sleep(sleep_time)
                waited += sleep_time

            if self._stop_event.is_set():
                break

            # Re-check config before running
            if self.config.LogCleaner_Enable and self.config.LogCleaner_ScheduledClean:
                logger.info("LogCleaner: Running scheduled clean")
                self.clean_logs()

        logger.info("LogCleaner: Scheduler thread stopped")

    def start_scheduler(self):
        """
        Start the background scheduler thread for scheduled cleaning.
        Only starts if scheduled clean is enabled.
        """
        if not self.config.LogCleaner_Enable:
            return
        if not self.config.LogCleaner_ScheduledClean:
            return
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return

        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="LogCleanerScheduler",
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop_scheduler(self):
        """
        Signal the scheduler thread to stop.
        """
        self._stop_event.set()
