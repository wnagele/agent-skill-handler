import argparse
import json
import sys
from pathlib import Path


class Skill:
    """Generic skill handler for OpenFang (JSON protocol) and OpenClaw (CLI).

    Tool definitions are the single source of truth for both the JSON
    protocol interface and the CLI.

    Usage:

        from skill_handler import Skill

        skill = Skill("myskill", "My Skill Description")

        @skill.tool("do_something",
            description="Does something useful",
            params={
                "name": {"type": "string", "description": "The name",
                         "required": True, "cli_positional": True},
                "verbose": {"type": "boolean", "description": "Verbose output"},
            })
        def do_something(input):
            return f"Did something with {input['name']}"

        if __name__ == "__main__":
            skill.run()
    """

    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self._tools = {}

    def tool(self, name, description="", params=None):
        if params is None:
            params = {}

        def decorator(fn):
            self._tools[name] = {
                "handler": fn,
                "description": description,
                "params": params,
                "required": [k for k, v in params.items() if v.get("required")],
            }
            return fn
        return decorator

    def run(self):
        if "--update-manifest" in sys.argv:
            self.update_manifest(Path("skill.toml"))
        elif len(sys.argv) <= 1:
            self._run_json()
        else:
            self._run_cli()

    # ------------------------------------------------------------------
    # JSON protocol
    # ------------------------------------------------------------------

    def _run_json(self):
        raw = sys.stdin.read()
        if not raw.strip():
            self._json_respond(error="Empty input on stdin")
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            self._json_respond(error=f"Invalid JSON: {e}")
            return

        tool_name = payload.get("tool", "")
        input_data = payload.get("input") or {}

        prefix = self.name + "_"
        if tool_name.startswith(prefix):
            tool_name = tool_name[len(prefix):]

        tool = self._tools.get(tool_name)
        if not tool:
            self._json_respond(error=f"Unknown tool: {tool_name}")
            return

        try:
            result = tool["handler"](input_data)
            self._json_respond(result=result)
        except Exception as e:
            self._json_respond(error=str(e))

    def _json_respond(self, result=None, error=None):
        if error is not None:
            print(json.dumps({"error": error}), flush=True)
        else:
            print(json.dumps({"result": result}), flush=True)

    # ------------------------------------------------------------------
    # CLI
    # ------------------------------------------------------------------

    def _run_cli(self):
        parser = self._build_parser()
        args = parser.parse_args()

        tool = self._tools[args._tool_name]

        input_data = {}
        for param_name, schema in tool["params"].items():
            value = getattr(args, param_name, None)
            if value is not None:
                input_data[param_name] = value
            elif schema.get("type") == "array" and value == []:
                pass
            elif schema.get("type") == "boolean" and value is False:
                pass

        try:
            result = tool["handler"](input_data)
            if result:
                print(result)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def _build_parser(self):
        parser = argparse.ArgumentParser(
            prog=f"{self.name}-cli.py",
            description=self.description,
        )
        top = parser.add_subparsers(dest="command", required=True)

        groups = {}
        for tool_name in self._tools:
            parts = tool_name.split("_", 1)
            group = parts[0]
            sub = parts[1] if len(parts) > 1 else None
            groups.setdefault(group, []).append((tool_name, sub))

        for group, tools in groups.items():
            if len(tools) == 1 and tools[0][1] is None:
                tool_name = tools[0][0]
                tool = self._tools[tool_name]
                sub_parser = top.add_parser(group, help=tool["description"])
                sub_parser.set_defaults(_tool_name=tool_name)
                self._add_params(sub_parser, tool)
            else:
                group_parser = top.add_parser(group)
                group_subs = group_parser.add_subparsers(
                    dest="subcommand", required=True,
                )
                for tool_name, sub in tools:
                    tool = self._tools[tool_name]
                    cli_sub = sub.replace("_", "-") if sub else group
                    sub_parser = group_subs.add_parser(
                        cli_sub, help=tool["description"],
                    )
                    sub_parser.set_defaults(_tool_name=tool_name)
                    self._add_params(sub_parser, tool)

        return parser

    def _add_params(self, parser, tool):
        for name, schema in tool["params"].items():
            ptype = schema.get("type", "string")
            desc = schema.get("description")
            choices = schema.get("enum")
            is_required = name in tool["required"]
            kwargs = {}
            if desc:
                kwargs["help"] = desc
            if choices:
                kwargs["choices"] = choices

            if schema.get("cli_positional"):
                if ptype == "integer":
                    kwargs["type"] = int
                elif ptype == "number":
                    kwargs["type"] = float
                if not is_required:
                    kwargs["nargs"] = "?"
                    kwargs["default"] = schema.get("default")
                parser.add_argument(name, **kwargs)
            elif ptype == "boolean":
                flag = "--" + name.replace("_", "-")
                parser.add_argument(flag, dest=name, action="store_true",
                                    **kwargs)
            elif ptype == "array":
                flag = "--" + name.replace("_", "-")
                parser.add_argument(flag, dest=name, action="append",
                                    default=[], **kwargs)
            else:
                flag = "--" + name.replace("_", "-")
                if ptype == "integer":
                    kwargs["type"] = int
                elif ptype == "number":
                    kwargs["type"] = float
                kwargs["default"] = schema.get("default")
                parser.add_argument(flag, dest=name, **kwargs)

    # ------------------------------------------------------------------
    # Manifest generation
    # ------------------------------------------------------------------

    def update_manifest(self, skill_toml_path):
        text = skill_toml_path.read_text()
        lines = text.splitlines(keepends=True)

        first_tool = None
        last_tool_end = None
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped == "[[tools.provided]]":
                if first_tool is None:
                    first_tool = i
                i += 1
                while (i < len(lines)
                       and lines[i].strip()
                       and lines[i].strip() != "[[tools.provided]]"
                       and not lines[i].strip().startswith("[")):
                    i += 1
                last_tool_end = i
            else:
                i += 1

        new_tools = self._generate_tools_block()

        if first_tool is not None:
            before = "".join(lines[:first_tool]).rstrip("\n") + "\n"
            after = "".join(lines[last_tool_end:])
            result = before + new_tools + after
        else:
            result = text.rstrip("\n") + "\n" + new_tools

        skill_toml_path.write_text(result)

    def _generate_tools_block(self):
        lines = []
        for name, tool in self._tools.items():
            full_name = f"{self.name}_{name}"
            schema = self._tool_schema(tool)

            lines.append("")
            lines.append("[[tools.provided]]")
            lines.append(f'name = "{full_name}"')
            lines.append(f'description = "{tool["description"]}"')
            lines.append(f"input_schema = {_toml_inline(schema)}")

        return "\n".join(lines) + "\n"

    def _tool_schema(self, tool):
        properties = {}
        for name, schema in tool["params"].items():
            prop = {}
            for key in ("type", "description", "enum", "items"):
                if key in schema:
                    prop[key] = schema[key]
            properties[name] = prop

        result = {"type": "object", "properties": properties}
        if tool["required"]:
            result["required"] = tool["required"]
        return result


def _toml_inline(value):
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_inline(v) for v in value) + "]"
    if isinstance(value, dict):
        parts = [f"{k} = {_toml_inline(v)}" for k, v in value.items()]
        return "{ " + ", ".join(parts) + " }"
    return str(value)
