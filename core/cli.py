import json
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.history import InMemoryHistory
from pyboxen import boxen

from core.cli_chat import CliChat

BANNER = """
 ███████╗██╗██╗     ███████╗███████╗ █████╗  ██████╗ ███████╗
 ██╔════╝██║██║     ██╔════╝██╔════╝██╔══██╗██╔════╝ ██╔════╝
 █████╗  ██║██║     █████╗  ███████╗███████║██║  ███╗█████╗  
 ██╔══╝  ██║██║     ██╔══╝  ╚════██║██╔══██║██║   ██║██╔══╝  
 ██║     ██║███████╗███████╗███████║██║  ██║╚██████╔╝███████╗
 ╚═╝     ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
 Intelligent File System Agent  ·  Type your query or /help
"""

HELP_TEXT = """
Commands:
  /help                         — Show this message
  /prompts                      — List available prompt templates
  /prompt <name> [arg=val ...]  — Run a prompt template (e.g. /prompt summarize_file file_path=main.py)
  /resources                    — List available resources
  /reset                        — Clear conversation history
  /quit                         — Exit FileSage

Or just type naturally:
  "summarize main.py"
  "search for TODO comments in *.py files"
  "what files are in /path/to/dir?"
  "auto-tag the file at /path/to/file.py"
"""


class CliApp:
    def __init__(self, agent: CliChat):
        self.agent = agent
        self.history = InMemoryHistory()
        self.session = PromptSession(
            history=self.history,
            style=Style.from_dict({
                "prompt": "#00ff88 bold",
                "completion-menu.completion": "bg:#1a1a1a #ffffff",
                "completion-menu.completion.current": "bg:#333333 #ffffff",
            }),
            complete_while_typing=True,
        )

    async def initialize(self):
        print(BANNER)

    async def run(self):
        while True:
            try:
                user_input = await self.session.prompt_async("filesage › ")
                if not user_input.strip():
                    continue

                # Built-in slash commands
                if user_input.strip() == "/quit":
                    print("Bye.")
                    break
                if user_input.strip() == "/help":
                    print(HELP_TEXT)
                    continue
                if user_input.strip() == "/reset":
                    self.agent.reset()
                    print("History cleared.\n")
                    continue
                if user_input.strip() == "/prompts":
                    prompts = await self.agent.list_prompts()
                    for p in prompts:
                        print(f"  • {p.name} — {p.description or ''}")
                    print()
                    continue
                if user_input.strip() == "/resources":
                    resources = await self.agent.list_resources()
                    for r in resources:
                        print(f"  • {r.uri} — {r.description or ''}")
                    print()
                    continue

                if user_input.strip().startswith("/prompt "):
                    parts = user_input.strip().split()
                    if len(parts) < 2:
                        print("Usage: /prompt <prompt_name> [arg1=value1 arg2=value2 ...]\n")
                        continue
                    prompt_name = parts[1]
                    args = {}
                    for part in parts[2:]:
                        if "=" in part:
                            k, v = part.split("=", 1)
                            args[k] = v
                    try:
                        messages = await self.agent.get_prompt(prompt_name, args)
                        prompt_text = ""
                        for msg in messages:
                            content = msg.content
                            if hasattr(content, "text"):
                                prompt_text += content.text + "\n"
                            elif isinstance(content, dict) and "text" in content:
                                prompt_text += content["text"] + "\n"
                            elif hasattr(msg, "content") and isinstance(msg.content, str):
                                prompt_text += msg.content + "\n"
                        prompt_text = prompt_text.strip()
                        if not prompt_text:
                            print("Prompt generated no text content.\n")
                            continue
                        print(f"[Prompt: {prompt_name}] Sending expanded prompt to LLM:")
                        print("-" * 50)
                        print(prompt_text)
                        print("-" * 50 + "\n")
                        user_input = prompt_text
                    except Exception as e:
                        print(f"Error executing prompt: {e}\n")
                        continue

                print()
                tool_calls: dict[int, dict] = {}

                async def handle_event(event):
                    if not hasattr(event, "type"):
                        return

                    if event.type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if not delta:
                            return
                        if delta.type == "text_delta":
                            print(delta.text, end="", flush=True)
                        elif delta.type == "input_json_delta":
                            idx = event.index
                            if idx not in tool_calls:
                                tool_calls[idx] = {"name": "", "args": ""}
                            tool_calls[idx]["args"] += delta.partial_json

                    elif event.type == "content_block_start":
                        cb = getattr(event, "content_block", None)
                        if cb and cb.type == "tool_use":
                            idx = getattr(event, "index", 0)
                            if idx not in tool_calls:
                                tool_calls[idx] = {"name": "", "args": ""}
                            tool_calls[idx]["name"] = cb.name
                            print()

                    elif event.type == "content_block_stop":
                        idx = event.index
                        if idx in tool_calls:
                            name = tool_calls[idx]["name"]
                            args_raw = tool_calls[idx]["args"]
                            try:
                                args = json.dumps(json.loads(args_raw), indent=2)
                            except Exception:
                                args = args_raw

                            box = boxen(
                                f"🔧 {name}\n\nArguments:\n{args}",
                                title="Tool Call",
                                style="rounded",
                                color="cyan",
                                padding=0,
                            )
                            print(box)
                            del tool_calls[idx]

                use_stream = self.agent.supports_stream
                response_text = await self.agent.run(
                    user_input,
                    stream=use_stream,
                    on_event=handle_event if use_stream else None,
                )
                if not use_stream:
                    print(response_text)
                print("\n")

            except KeyboardInterrupt:
                print("\nBye.")
                break
            except Exception as e:
                print(f"\n[error] {e}\n")