# AGENTS.md - Coding Guidelines for AzurLaneAutoScript

This document provides essential information for AI coding agents working on the AzurLaneAutoScript (Alas) codebase.

## Project Overview

Alas is a 24/7 automation bot for Azur Lane with a web GUI. It's designed for long-running scenarios with extensive error recovery. The codebase is Python-based, targeting Python 3.7+ (requirements.txt compiled for 3.7).

## Running the Application

### Main Entry Points
- **GUI/Web Interface**: `python gui.py` - Starts uvicorn web server on port 22267
- **CLI Mode**: `python alas.py` - Direct script execution
- **Executable**: `Alas.exe` - Pre-built Windows executable (recommended for Windows)

### Command Line Arguments (gui.py)
```bash
python gui.py --host 0.0.0.0 --port 22267
python gui.py --ssl-key <path> --ssl-cert <path>  # HTTPS support
python gui.py --run <config_name>  # Auto-start specific config
```

### Correct Way to Run/Debug Alas

**❌ Wrong**: Using system Python directly
```bash
python gui.py  # May fail with missing dependencies
```

**✅ Correct**: Use toolkit's bundled Python
```bash
# Windows
.\toolkit\python.exe gui.py
.\toolkit\python.exe -c "from module.config.config import AzurLaneConfig; ..."

# Or use Alas.exe which handles environment setup
.\Alas.exe
```

The toolkit contains all required dependencies. System Python may lack packages like `cached_property`, `rich`, etc.

## Testing

### Test Execution
**No formal test suite exists.** The project uses manual testing and dev tools instead.

Existing test files (for reference only):
- `dev_tools/emulator_test.py` - Emulator connection testing
- `deploy/Windows/installer_test.py` - Installer validation

### Dev Tools
Located in `dev_tools/`, these are manual testing utilities:
- `button_extract.py` - Extract UI button coordinates
- `map_extractor.py` - Extract campaign map data
- `relative_crop.py` - Crop and analyze screenshots
- `grids_debug.py` - Debug map grid detection

**Running dev tools**: Execute directly, e.g., `python dev_tools/button_extract.py`

## Code Style Guidelines

### Import Organization
Follow this order (no blank lines between groups):
```python
# 1. Standard library
import os
import threading
from datetime import datetime, timedelta

# 2. Third-party packages
import inflection
from cached_property import cached_property
from PIL import Image

# 3. Local modules (absolute imports only)
from module.base.button import Button
from module.base.decorator import cached_property
from module.config.config import AzurLaneConfig
from module.device.device import Device
from module.logger import logger
```

**Rules**:
- Use absolute imports: `from module.base.button import Button`
- Never use relative imports: `from .button import Button` ❌
- Asset imports use wildcard: `from module.ui.assets import *`
- Group by: stdlib → third-party → local, but no blank lines

### Formatting
- **Indentation**: 4 spaces (Python standard)
- **Line length**: No strict limit, but keep reasonable (~120 chars)
- **Quotes**: Single quotes `'string'` preferred, double quotes for docstrings
- **Trailing whitespace**: Remove (except in markdown)
- **Final newline**: Required in all files

### Naming Conventions
- **Classes**: `PascalCase` - `ModuleBase`, `AzurLaneConfig`, `CampaignBase`
- **Functions/Methods**: `snake_case` - `run_campaign()`, `get_next_task()`
- **Constants**: `UPPER_SNAKE_CASE` - `DEFAULT_TIME`, `VALID_SERVER`
- **Private members**: `_leading_underscore` - `_button_offset`, `_match_init`
- **Buttons/Assets**: `UPPER_SNAKE_CASE` - `BATTLE_PREPARATION`, `GOTO_MAIN`
- **Module variables**: `snake_case` - `config`, `device`, `logger`

### Type Hints
**Minimal usage.** Type hints are optional and rarely used:
```python
# Acceptable (class attributes)
config: AzurLaneConfig
device: Device
stop_event: threading.Event = None

# Acceptable (function signatures in new code)
def func(ev: threading.Event) -> bool:
    pass

# Not required for most functions
def run(self, command, skip_first_screenshot=False):  # No return type needed
    pass
```

### Docstrings
Use triple double-quotes. Format varies - both Google and simple styles are acceptable:
```python
def __init__(self, config, device=None, task=None):
    """
    Args:
        config (AzurLaneConfig, str):
            Name of the user config under ./config
        device (Device, str):
            To reuse a device. If None, create a new Device object.
        task (str):
            Bind a task only for dev purpose.
    """
```

### Comments
- Use inline comments sparingly for complex logic
- Prefer self-documenting code
- Comment "why" not "what"

## Architecture Patterns

### Class Inheritance
Common inheritance chains:
```python
ModuleBase → CampaignUI → Map → AutoSearchCombat → CampaignBase
AzurLaneConfig(ConfigUpdater, ManualConfig, GeneratedConfig, ConfigWatcher)
Device(Screenshot, Control, AppControl, Input)
```

### Decorators
- `@cached_property` - Lazy initialization, cache result (from `cached_property` package)
- `@Config.when(CONDITION=True)` - Conditional method overrides based on config
- `@del_cached_property` - Invalidate cached properties

Example:
```python
@cached_property
def device(self):
    from module.device.device import Device
    return Device(config=self.config)
```

### Exception Handling
Use custom exceptions for control flow (defined in `module/exception.py`):
```python
try:
    self.run_campaign()
except TaskEnd:
    return True
except GameStuckError as e:
    logger.error(e)
    self.config.task_call('Restart')
    return False
except RequestHumanTakeover:
    logger.critical('Request human takeover')
    exit(1)
```

**Common exceptions**:
- `TaskEnd` - Normal task completion
- `GameStuckError` - Game UI stuck, needs restart
- `GameNotRunningError` - Game not running
- `RequestHumanTakeover` - Critical error, human intervention needed
- `ScriptError` - Developer mistake or random issue

### Logging
Use the custom logger from `module.logger`:
```python
from module.logger import logger

logger.hr('Section Title', level=0)  # Horizontal rule
logger.attr('Key', 'Value')          # Key-value pair
logger.info('Message')
logger.warning('Warning message')
logger.error('Error message')
logger.critical('Critical error')
```

## Error Handling Best Practices

1. **Catch specific exceptions** - Don't use bare `except:`
2. **Log before re-raising** - Use `logger.exception(e)` to capture traceback
3. **Use custom exceptions** - For game state management
4. **Exit on critical errors** - Use `exit(1)` for unrecoverable errors
5. **Retry on transient errors** - Implement retry logic for network/device issues

## Configuration

- **Config files**: JSON format in `config/` directory
- **Template**: `config/template.json` - Base configuration
- **User configs**: `config/<name>.json` - Per-user settings
- **Deploy config**: `config/deploy.yaml` - Deployment settings

### Adding New Configuration Options

When adding new configuration options, follow this workflow:

#### 1. Define Configuration in YAML Source Files

**Edit `module/config/argument/argument.yaml`**:
```yaml
AutoStart:
  Enable:
    type: checkbox
    value: false
  Delay: 10
```

**Edit `module/config/argument/task.yaml`** to bind the config group to a task:
```yaml
Alas:
  tasks:
    Alas:
      - Emulator
      - AutoStart  # Add your config group here
```

#### 2. Add Translations

**Edit `module/config/i18n/zh-CN.json`**:
```json
"AutoStart": {
  "_info": {
    "name": "自动启动",
    "help": "功能说明"
  },
  "Enable": {
    "name": "启用",
    "help": "详细说明"
  }
}
```

Repeat for `en-US.json`, `ja-JP.json`, `zh-TW.json`.

#### 3. Update Template Configuration

**Edit `config/template.json`**:
```json
"Alas": {
  "AutoStart": {
    "Enable": false,
    "Delay": 10
  }
}
```

#### 4. Regenerate Configuration Files

**Run the config generator**:
```bash
.\toolkit\python.exe -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"
```

This regenerates:
- `module/config/argument/args.json` - GUI control definitions
- `module/config/argument/menu.json` - Menu structure
- Updates all i18n files

#### 5. Access Configuration in Code

Configuration attributes are dynamically bound with underscore notation:

```python
from module.config.config import AzurLaneConfig

config = AzurLaneConfig('alas')
# Access: ConfigGroup_OptionName
if config.AutoStart_Enable:
    delay = config.AutoStart_Delay
```

**Important**: 
- Attribute names use underscore: `AutoStart_Enable` (not `Alas_AutoStart_Enable`)
- The config group name is omitted from the attribute name
- Raw data is in `config.data['Alas']['AutoStart']['Enable']`

### Configuration System Architecture

```
YAML Sources (argument.yaml, task.yaml)
    ↓ ConfigGenerator().generate()
JSON Files (args.json, menu.json, i18n/*.json)
    ↓ AzurLaneConfig.load()
Python Attributes (config.AutoStart_Enable)
```

### Common Configuration Pitfalls

- ❌ Don't edit `args.json` directly - it's auto-generated from YAML
- ❌ Don't forget to run `ConfigGenerator().generate()` after YAML changes
- ❌ Don't use `config.Alas_AutoStart_Enable` - use `config.AutoStart_Enable`
- ✅ Do edit YAML source files (`argument.yaml`, `task.yaml`)
- ✅ Do add translations to all i18n files
- ✅ Do regenerate configs after YAML changes

## File Organization

```
module/
├── base/          # Foundation classes (ModuleBase, Button, Timer)
├── config/        # Configuration management
├── device/        # Device control (ADB, screenshots, input)
├── logger.py      # Logging utilities
├── exception.py   # Custom exceptions
├── campaign/      # Battle/mission logic
├── ui/            # UI navigation
└── webui/         # Web interface

campaign/          # Map-specific implementations
dev_tools/         # Development utilities
assets/            # Image assets for recognition
```

## Key Principles

1. **Absolute imports only** - Never use relative imports
2. **Lazy initialization** - Use `@cached_property` for expensive resources
3. **Exception-driven flow** - Game states as exceptions
4. **Extensive logging** - Log all significant actions
5. **Config-driven behavior** - Avoid hardcoding, use config values
6. **Device abstraction** - All device operations through `Device` class
7. **Asset-based UI** - Use `Button` objects for screen recognition

## Advanced Topics

### Custom Status System
ALAS supports custom status messages displayed in the WebUI (e.g., "Running (Commission ships insufficient)"):

**Architecture**:
- Subprocess (task execution) writes status to `./config/.status_{config_name}`
- Main process (GUI) polls status file every 2 seconds
- Status codes defined in `module/config/i18n/*.json` under `Gui.Status`

**Adding new status**:
1. Write status code to file in task module: `self.config.write_status('status_code')`
2. Add translations to all i18n files: `"Gui.Status.StatusCode": "Display text"`
3. Status automatically cleared when scheduler starts

See `docs/status_system.md` for detailed implementation.

### Input Validation System
Configuration input validation is handled at the WebUI layer:

**Validation flow**:
1. User inputs value in WebUI
2. System validates against regex in `args.json` (from `argument.yaml`)
3. If valid: parse type and save; if invalid: show red border + error message

**Adding validation to config option**:
1. Add `validate: '^regex$'` to `module/config/argument/argument.yaml`
2. Add `invalid_feedback` translations to all `module/config/i18n/*.json` files
3. Run config generator: `.\toolkit\python.exe -c "from module.config.config_updater import ConfigGenerator; ConfigGenerator().generate()"`
4. Test in GUI

**Important**:
- Validation runs on **original string** before type conversion
- Only `type: input` fields need validation (checkbox/select/datetime have built-in validation)
- After adding WebUI validation, remove any backend defensive validation to avoid conflicts

See `docs/input-validation-spec.md` for complete guide and `docs/input-validation-lessons.md` for common pitfalls.

### Upstream Synchronization
This fork can sync with upstream `guoh064/AzurLaneAutoScript`:

**Automatic sync**: GitHub Actions runs daily at UTC 00:00
**Manual sync**: `git sync` (uses merge) or `git sync-clean` (uses rebase)

See `docs/upstream-sync-guide.md` for detailed workflow and conflict resolution.

## Additional Resources

- **Official Wiki**: https://github.com/LmeSzinc/AzurLaneAutoScript/wiki
- **Development Guide**: https://github.com/LmeSzinc/AzurLaneAutoScript/wiki/Development
- **Configuration Guide**: https://github.com/LmeSzinc/AzurLaneAutoScript/wiki/Configuration
- **Local Documentation**: See `docs/` folder for custom features and development guides

## Common Pitfalls

- ❌ Don't use relative imports
- ❌ Don't modify test files unless explicitly requested
- ❌ Don't add type hints everywhere (only where beneficial)
- ❌ Don't create new config files without understanding the config system
- ❌ Don't bypass the Device abstraction layer
- ❌ Don't use system Python - always use `.\toolkit\python.exe`
- ❌ Don't edit generated JSON files directly - edit YAML sources instead
- ❌ Don't add validation to `argument.yaml` without running ConfigGenerator
- ❌ Don't put display text in `argument.yaml` - use i18n files for multilingual support
- ❌ Don't keep backend validation after adding WebUI validation (causes conflicts)
- ✅ Do use the logger for all output
- ✅ Do follow the existing inheritance patterns
- ✅ Do use custom exceptions for control flow
- ✅ Do test with actual game screenshots when possible
- ✅ Do regenerate configs after modifying YAML files
- ✅ Do validate regex on original string before type conversion
- ✅ Do add translations to all 4 i18n files (zh-CN, en-US, ja-JP, zh-TW)
