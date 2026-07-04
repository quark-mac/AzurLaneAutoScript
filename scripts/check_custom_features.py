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
    )
    for lang in LANGS:
        data = load_json('module/config/i18n/%s.json' % lang)
        for path in required:
            value = deep_get(data, path)
            check(value not in (None, ''), 'Missing i18n path for %s: %s' % (lang, path), errors)


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
    )
    for text in required_task_text:
        check(text in task_yaml, 'Missing task.yaml entry containing: %s' % text.strip(), errors)


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
