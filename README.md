# skill_handler.py

A generic framework for building skills that work with both OpenFang (JSON protocol) and OpenClaw (CLI) from a single set of tool definitions.

## Quick start

```python
from skill_handler import Skill

skill = Skill("weather", "Weather lookup skill")

@skill.tool("current",
    description="Get current weather for a location",
    params={
        "location": {"type": "string", "required": True, "cli_positional": True,
                      "description": "City name or coordinates"},
        "units":    {"type": "string", "enum": ["metric", "imperial"],
                      "description": "Unit system"},
    })
def current(input):
    location = input["location"]
    units = input.get("units", "metric")
    # ... fetch weather ...
    return f"Weather in {location}: 22C, sunny"

if __name__ == "__main__":
    skill.run()
```

This single definition gives you three things:

1. **OpenFang JSON protocol** (no args):
   ```
   echo '{"tool": "weather_current", "input": {"location": "Berlin"}}' | python3 weather.py
   → {"result": "Weather in Berlin: 22C, sunny"}
   ```

2. **CLI** (with args):
   ```
   python3 weather.py current Berlin --units metric
   → Weather in Berlin: 22C, sunny
   ```

3. **Manifest generation**:
   ```
   python3 weather.py --update-manifest
   ```
   Updates the `[[tools.provided]]` sections in `skill.toml`, preserving all other sections.

## Modes

`skill.run()` picks the mode based on `sys.argv`:

| Invocation | Mode |
|---|---|
| `python3 skill.py` | JSON protocol — reads `{"tool": "...", "input": {...}}` from stdin, writes `{"result": "..."}` or `{"error": "..."}` to stdout |
| `python3 skill.py <command> [args]` | CLI — argparse generated from tool params |
| `python3 skill.py --update-manifest` | Regenerates `[[tools.provided]]` in `skill.toml` |

## Defining tools

### `@skill.tool(name, description, params)`

- **name** — Tool name without the skill prefix. Underscores encode the CLI subcommand hierarchy: `recipe_search` becomes `recipe search` on the CLI and `<prefix>_recipe_search` in the OpenFang protocol.
- **description** — Human-readable description. Used in CLI `--help` and in `skill.toml`.
- **params** — Dict of param definitions. Each key is the param name, each value is a schema dict.

### Param schema

| Key | Type | Description |
|---|---|---|
| `type` | string | `"string"`, `"integer"`, `"number"`, `"boolean"`, or `"array"` |
| `description` | string | Human-readable description |
| `required` | bool | If true, param is required |
| `enum` | list | Restrict values to this set |
| `items` | dict | For `"array"` type — schema of array items (e.g. `{"type": "string"}`) |
| `default` | any | Default value (CLI only) |
| `cli_positional` | bool | If true, rendered as a positional arg in the CLI instead of `--flag` |

### CLI mapping

The param schema maps to argparse as follows:

| Schema | argparse |
|---|---|
| `"type": "string"` | `--name VALUE` |
| `"type": "integer"` | `--name VALUE` with `type=int` |
| `"type": "boolean"` | `--name` (store_true) |
| `"type": "array"` | `--name VALUE` (repeatable, append) |
| `"cli_positional": true` | Positional arg |
| `"enum": [...]` | `choices=[...]` |
| `"required": true` + positional | Required positional |
| Not required + positional | Optional positional (`nargs="?"`) |

Underscores in param names become hyphens in CLI flags: `order_by` becomes `--order-by`.

### Tool name to CLI subcommand mapping

The tool name is split on the first underscore to determine the command group and subcommand:

| Tool name | CLI command |
|---|---|
| `recipe_search` | `recipe search` |
| `recipe_parse_ingredients` | `recipe parse-ingredients` |
| `mealplan_today` | `mealplan today` |
| `organizers_list` | `organizers list` |

Remaining underscores after the first split become hyphens in the subcommand name.

## Handlers

Handlers receive an `input` dict and return a string:

```python
@skill.tool("greet", ...)
def greet(input):
    return f"Hello, {input['name']}!"
```

- **Return value** — printed to stdout (CLI) or wrapped in `{"result": "..."}` (JSON).
- **Exceptions** — printed to stderr with exit code 1 (CLI) or wrapped in `{"error": "..."}` (JSON).
- **stderr** — use `print(..., file=sys.stderr)` for warnings. These pass through in both modes.

## Manifest generation

```
python3 myscript.py --update-manifest
```

Reads and updates `skill.toml` in the current working directory. This replaces all `[[tools.provided]]` sections in the file with entries generated from the `@skill.tool` decorators. Everything else in the file is preserved.

Run this whenever you add, remove, or change tool definitions to keep `skill.toml` in sync.

## Project layout

```
my-skill/
  SKILL.md              # OpenClaw skill definition
  skill.toml            # OpenFang manifest (tools section generated)
  scripts/
    skill_handler.py    # This framework (copy into your skill)
    myskill.py          # Your skill implementation
```

`skill.toml` `[runtime]` entry should point to your skill script:

```toml
[runtime]
type = "python"
entry = "scripts/myskill.py"
```
