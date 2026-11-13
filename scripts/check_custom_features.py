import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGS = ('zh-CN', 'en-US', 'ja-JP', 'zh-TW')


def read_text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def load_json(path):
    return json.loads(read_text(path))


def deep_get(data, path):
    current = data
    for key in path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def check(condition, message, errors):
    if not condition:
        errors.append(message)


def check_config_generated(errors):
    text = read_text('module/config/config_generated.py')
    attrs = set(re.findall(r'^    ([A-Za-z][A-Za-z0-9_]+)\s*=', text, re.M))
    required = (
        'AutoStart_Enable',
        'AutoStart_Delay',
        'LogCleaner_Enable',
        'LogCleaner_CleanOnStartup',
        'LogCleaner_ScheduledClean',
        'LogCleaner_ScheduledTime',
        'LogCleaner_KeepDays',
        'Commission_EnableShipCheck',
        'Commission_ShipCheckTimeout',
    )
    for attr in required:
        check(attr in attrs, 'Missing generated config attribute: %s' % attr, errors)


def check_template(errors):
    template = load_json('config/template.json')
    required = (
        'Alas.AutoStart.Enable',
        'Alas.AutoStart.Delay',
        'Alas.LogCleaner.Enable',
        'Alas.LogCleaner.CleanOnStartup',
        'Alas.LogCleaner.ScheduledClean',
        'Alas.LogCleaner.ScheduledTime',
        'Alas.LogCleaner.KeepDays',
        'Commission.Commission.EnableShipCheck',
        'Commission.Commission.ShipCheckTimeout',
    )
    for path in required:
        check(deep_get(template, path) is not None, 'Missing template config path: %s' % path, errors)


def check_argument_sources(errors):
    argument_yaml = read_text('module/config/argument/argument.yaml')
    required_argument_text = (
        'AutoStart:',
        '  Enable:',
        '  Delay:',
        'LogCleaner:',
        '  CleanOnStartup:',
        '  ScheduledClean:',
        '  ScheduledTime:',
        '  KeepDays:',
        'Commission:',
        '  EnableShipCheck:',
        '  ShipCheckTimeout:',
    )
    for text in required_argument_text:
        check(text in argument_yaml, 'Missing argument.yaml entry containing: %s' % text.strip(), errors)

    gui_yaml = read_text('module/config/argument/gui.yaml')
    check(
        '  CommissionShipInsufficient:' in gui_yaml,
        'Missing gui.yaml status entry: CommissionShipInsufficient',
        errors,
    )


def check_i18n(errors):
    required = (
        'AutoStart._info.name',
        'AutoStart.Enable.name',
        'AutoStart.Delay.name',
        'LogCleaner._info.name',
        'LogCleaner.Enable.name',
        'LogCleaner.CleanOnStartup.name',
        'LogCleaner.ScheduledClean.name',
        'LogCleaner.ScheduledTime.name',
        'LogCleaner.KeepDays.name',
        'Commission.EnableShipCheck.name',
        'Commission.ShipCheckTimeout.name',
        'Gui.Status.CommissionShipInsufficient',
        'AutoStart.Delay.invalid_feedback',
        'LogCleaner.ScheduledTime.invalid_feedback',
        'LogCleaner.KeepDays.invalid_feedback',
    )
    for lang in LANGS:
        data = load_json('module/config/i18n/%s.json' % lang)
        for path in required:
            value = deep_get(data, path)
            check(value not in (None, '', path), 'Missing i18n path for %s: %s' % (lang, path), errors)


def check_task_entries(errors):
    alas = read_text('alas.py')
    required_methods = (
        'gems_farming',
        'island_production',
        'island_order',
        'island_freebie',
        'island_collect',
        'island_season_task',
        'island_business',
        'island_production_planner',
        'island_transport',
    )
    for method in required_methods:
        check(
            re.search(r'^    def %s\(' % re.escape(method), alas, re.M),
            'Missing Alas task method: %s' % method,
            errors,
        )

    task_yaml = read_text('module/config/argument/task.yaml')
    required_task_text = (
        '      - AutoStart',
        '      - LogCleaner',
        '    GemsFarming:',
        '    Commission:',
        '    IslandProduction:',
        '    IslandOrder:',
        '    IslandFreebie:',
        '    IslandCollect:',
        '    IslandSeasonTask:',
        '    IslandBusiness:',
        '    IslandProductionPlanner:',
        '    IslandTransport:',
    )
    for text in required_task_text:
        check(text in task_yaml, 'Missing task.yaml entry containing: %s' % text.strip(), errors)

    required_runtime_text = (
        'LogCleaner(config=self.config)',
        'log_cleaner.run_on_startup()',
        'log_cleaner.start_scheduler()',
    )
    for text in required_runtime_text:
        check(text in alas, 'Missing LogCleaner runtime integration: %s' % text, errors)

    gui = read_text('gui.py')
    check('config.AutoStart_Enable' in gui, 'Missing AutoStart runtime integration', errors)

    commission = read_text('module/commission/commission.py')
    check(
        'Commission_EnableShipCheck' in commission and 'Commission_ShipCheckTimeout' in commission,
        'Missing commission ship check runtime integration',
        errors,
    )


def check_input_validation(errors):
    argument_yaml = read_text('module/config/argument/argument.yaml')
    check(argument_yaml.count('validate:') >= 3, 'Missing custom input validation rules', errors)

    updater = read_text('module/config/config_updater.py')
    check(
        "words=('name', 'help', 'invalid_feedback')" in updater,
        'Missing invalid_feedback generation support',
        errors,
    )

    app = read_text('module/webui/app.py')
    check('re_fullmatch(validate, v_str)' in app, 'Missing WebUI regex validation', errors)
    save_config = app.split('    def _save_config(', 1)[-1].split('\n    def ', 1)[0]
    check(
        not re.search(r'pin\[.*?\]\s*=\s*(?:to_pin_value\()?default', save_config),
        'Empty WebUI fields still push defaults back immediately',
        errors,
    )
    check(
        0 <= save_config.find('re_fullmatch(validate, v_str)') < save_config.find('parse_pin_value(v, valuetype)'),
        'Input validation must run before type conversion',
        errors,
    )
    args = load_json('module/config/argument/args.json')
    cases = (
        ('AutoStart.Delay', ('0', '10', '600'), ('-1', '601', '1.5', 'abc')),
        ('LogCleaner.KeepDays', ('1', '7', '365'), ('0', '366', '-1', '1.5')),
        ('LogCleaner.ScheduledTime', ('00:00', '09:30', '23:59'), ('24:00', '12:60', '9:00', 'abc')),
    )
    for path, valid, invalid in cases:
        rule = deep_get(args, 'Alas.%s.validate' % path)
        check(bool(rule), 'Missing generated validation rule: %s' % path, errors)
        if rule:
            for value in valid + invalid:
                check(bool(re.fullmatch(rule, value)) == (value in valid),
                      'Validation boundary changed: %s = %s' % (path, value), errors)


def check_scheduler_controls(errors):
    override = read_text('module/config/argument/override.yaml')
    for task in ('Commission', 'Research', 'Reward'):
        pattern = r'%s:\n  Scheduler:\n    Enable:\n      type: lock' % task
        check(
            re.search(pattern, override) is None,
            'Scheduler enable is forced on for task: %s' % task,
            errors,
        )

    css = read_text('assets/gui/css/alas.css')
    check(
        '#pywebio-scope-Scheduler_Enable' not in css,
        'Scheduler enable checkbox is hidden by CSS',
        errors,
    )

    config = read_text('module/config/config.py')
    override = config.split('    def override(', 1)[-1].split('\n    config_override =', 1)[0]
    check(
        'Scheduler.Enable' not in override,
        'Scheduler enable is forced on by config loading',
        errors,
    )
    args = load_json('module/config/argument/args.json')
    template = load_json('config/template.json')
    for task in ('Commission', 'Tactical', 'Research', 'Dorm', 'Meowfficer', 'Guild', 'Reward', 'Freebies'):
        check(deep_get(args, '%s.Scheduler.Enable.type' % task) == 'checkbox',
              'Task enable is no longer editable: %s' % task, errors)
        check(deep_get(args, '%s.Scheduler.Enable.value' % task) is False
              and deep_get(template, '%s.Scheduler.Enable' % task) is False,
              'New configurations unexpectedly enable task: %s' % task, errors)
    connection = read_text('module/device/connection_attr.py')
    check('chr(8)' not in connection and "if 'oc' in v['type']" not in connection,
          'Device connection depends on locked config controls again', errors)


def check_update_and_status(errors):
    updater = read_text('module/webui/updater.py')
    install = updater.split('    def git_install(self):', 1)[-1].split('\n    @', 1)[0]
    check(
        'self.git_repository_init(' in install and 'super().git_install()' not in install,
        'Manual WebUI update must bypass startup AutoUpdate and propagate Git errors',
        errors,
    )
    check(
        'return []' in updater.split('    def get_commit(', 1)[-1].split('\n    def ', 1)[0],
        'Empty commit history must return a list for multiple commits',
        errors,
    )
    for path in ('deploy/git.py', 'deploy/Windows/git.py'):
        check(
            'Continue startup without update' in read_text(path),
            'Missing startup recovery after Git update failure: %s' % path,
            errors,
        )
    for path, text in (
        ('gui.py', 'while not State._init:'),
        ('module/commission/commission.py', 'commission_ship_insufficient'),
        ('module/webui/process_manager.py', 'def custom_status_message('),
        ('module/webui/app.py', 'custom_status_message'),
        ('module/webui/app.py', 'get_state=self.get_status_with_message'),
        ('module/webui/app.py', 'return (state, msg)'),
        ('alas.py', 'os.remove(status_file)'),
    ):
        check(text in read_text(path), 'Missing custom runtime behavior in %s: %s' % (path, text), errors)


def check_log_cleaner_and_fork_fixes(errors):
    cleaner = read_text('module/log_cleaner.py')
    for text in ('def _clean_log_files(', 'def _clean_error_dirs(', 'def _clean_screenshots(',
                 'self.config.DropRecord_SaveFolder', 'file_date < cutoff_date', 'ts < cutoff_ms',
                 'root != screenshot_dir', 'LogCleaner_CleanOnStartup', 'LogCleaner_ScheduledClean',
                 'self._scheduler_thread.is_alive()', 'self._stop_event.set()'):
        check(text in cleaner, 'Missing LogCleaner behavior: %s' % text, errors)
    for path, text in (
        ('module/os/map.py', "self.config.task_call('OpsiHazard1Leveling')"),
        ('module/shop_event/ui.py', 'class EventShopScroll(Scroll):'),
        ('module/config/config_updater.py', 'legacy_waitress_to_slots'),
        ('campaign/event_20260625_cn/t1.py', "MAP_ENSURE_EDGE_INSIGHT_CORNER = 'bottom'"),
        ('campaign/event_20260625_cn/ht1.py', "MAP_ENSURE_EDGE_INSIGHT_CORNER = 'bottom'"),
    ):
        check(text in read_text(path), 'Missing retained fork fix in %s: %s' % (path, text), errors)


def check_files(errors):
    required_files = (
        'module/log_cleaner.py',
        'module/campaign/gems_farming.py',
        'module/equipment/equipment_code.py',
        'module/island/production.py',
        'module/island/order.py',
        'module/island/freebie.py',
        'module/island/collect.py',
        'module/island/season_task.py',
        'module/island/business.py',
        'module/island_handler/production_planner.py',
        'module/island/transport.py',
    )
    for path in required_files:
        check((ROOT / path).exists(), 'Missing custom feature file: %s' % path, errors)


def main():
    errors = []
    check_config_generated(errors)
    check_template(errors)
    check_argument_sources(errors)
    check_i18n(errors)
    check_task_entries(errors)
    check_input_validation(errors)
    check_scheduler_controls(errors)
    check_update_and_status(errors)
    check_log_cleaner_and_fork_fixes(errors)
    check_files(errors)

    if errors:
        print('Custom feature health check failed:')
        for error in errors:
            print('- %s' % error)
        return 1

    print('Custom feature health check passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
