import asyncio
import json
import os
import time
from dotenv import load_dotenv
load_dotenv()
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# mcp installations
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp.types as mcp_types

# llm - google gen ai installation
from google import genai
from google.genai import types as genai_types

# Gemini client
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

client = genai.Client(api_key=api_key)

# ---------- Simple config ----------
MODEL = "gemini-2.0-flash"  # Pro model for better reasoning
MAX_STEPS = 15
HEADLESS = True
DEFAULT_START_URL = "https://www.saucedemo.com/"
# ----------------------------------

SYSTEM_INSTRUCTION = """You are a web-automation planner.
Each turn, CALL EXACTLY ONE function:
- a browser_* tool to act, OR
- finish_success(message), OR
- finish_failure(reason).

CRITICAL: The snapshot contains elements with "ref" values (e.g., e11, e25, e42).
To interact with elements, you MUST:
1. Find the element in the snapshot (look for textboxes, buttons, links, etc.)
2. Use BOTH element (human description) AND ref (exact value like "e11")

WORKFLOW FOR SHOPPING:
1. Login → Enter credentials and click login
2. Add item to cart → Click "Add to cart" button for desired item
3. Go to cart → Look for "shopping_cart_link" or badge with cart count, click it
4. Review cart → Check prices and items in cart
5. Complete goal → Call finish_success with the information

CRITICAL RULES:
- If you see a shopping cart badge or link (look for refs containing "cart" or "badge"), CLICK IT to view cart
- Don't click the same button more than twice
- After adding items, your NEXT action should be clicking the cart icon/link
- The cart typically shows as a link or badge in the header/navigation area
- Look for elements with "cart" in their test-id or description

Example sequence:
- browser_type to enter username
- browser_type to enter password  
- browser_click on login button
- browser_click on "add to cart" for item
- browser_click on shopping cart badge/link (THIS IS CRITICAL - look for cart icon with item count)
- Read prices from snapshot
- finish_success with details

Look at the snapshot carefully. When goal is reached, call finish_success with details.
If blocked, call finish_failure with reason.
"""

USER_PRIMER = """Inputs you receive each turn:
- goal: user's desired outcome
- start_url: optional starting URL
- last_tool_result: text result of your last tool call (review this to avoid repeating failed actions)
- snapshot: structured page snapshot with element refs

Respond ONLY by calling one function.
Do not repeat the same action if it didn't achieve progress.
"""


# ---- Minimal tool declarations (what the model can call) ----
def fn_finish_success():
    return {
        "name": "finish_success",
        "description": "Task is complete; return a final message.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"message": {"type": "STRING"}},
            "required": ["message"],
        },
    }


def fn_finish_failure():
    return {
        "name": "finish_failure",
        "description": "Stop early; explain briefly why it failed or is blocked.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"reason": {"type": "STRING"}},
            "required": ["reason"],
        },
    }


# Browser tool schemas - match MCP Playwright server exactly
FN_BROWSER_TOOLS = [
    {
        "name": "browser_navigate",
        "description": "Navigate to a URL.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"url": {"type": "STRING"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_click",
        "description": "Click an element. Use element (description) and ref (from snapshot).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element": {"type": "STRING", "description": "Human-readable element description"},
                "ref": {"type": "STRING", "description": "Exact element reference from snapshot (e.g., e11, e25)"}
            },
            "required": ["element", "ref"],
        },
    },
    {
        "name": "browser_type",
        "description": "Type text into an element. Use element (description) and ref (from snapshot).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element": {"type": "STRING", "description": "Human-readable element description"},
                "ref": {"type": "STRING", "description": "Exact element reference from snapshot (e.g., e11, e25)"},
                "text": {"type": "STRING", "description": "Text to type"},
                "submit": {"type": "BOOLEAN", "description": "Press Enter after typing"}
            },
            "required": ["element", "ref", "text"],
        },
    },
    {
        "name": "browser_wait_for",
        "description": "Wait for text to appear or time to pass.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "Text to wait for"},
                "time": {"type": "NUMBER", "description": "Seconds to wait"}
            },
        },
    },
    {
        "name": "browser_snapshot",
        "description": "Get accessibility snapshot with element refs.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]


def _stringify_tool_result(result: mcp_types.CallToolResult) -> str:
    """Return tool result as plain text."""
    if getattr(result, "structuredContent", None):
        try:
            return json.dumps(result.structuredContent, ensure_ascii=False)
        except Exception:
            pass
    pieces: List[str] = []
    for block in (result.content or []):
        if isinstance(block, mcp_types.TextContent):
            pieces.append(block.text)
        else:
            pieces.append(repr(block))
    return "\n".join(pieces).strip()


class MCPBrowser:
    """Small wrapper around the Playwright MCP server over stdio."""

    def __init__(self, headless: bool = True):
        args = ["@playwright/mcp@latest"]
        if headless:
            args.append("--headless")
        self._server_params = StdioServerParameters(command="npx", args=args, env=os.environ.copy())
        self._session: ClientSession | None = None

    async def __aenter__(self):
        self._client_ctx = stdio_client(self._server_params)
        self._streams = await self._client_ctx.__aenter__()
        read, write = self._streams
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._session:
                await self._session.__aexit__(exc_type, exc, tb)
            await self._client_ctx.__aexit__(exc_type, exc, tb)
        except Exception:
            # Suppress all cleanup errors
            pass

    async def call(self, tool: str, args: Dict[str, Any]) -> str:
        assert self._session is not None
        result = await self._session.call_tool(tool, arguments=args)
        return _stringify_tool_result(result)

    async def list_tools(self) -> Dict[str, mcp_types.Tool]:
        assert self._session is not None
        tools = await self._session.list_tools()
        return {t.name: t for t in tools.tools}


async def run_agent(goal: str, start_url: str) -> Tuple[bool, str]:
    """Minimal control loop: snapshot -> ask LLM -> call chosen tool."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return False, "GEMINI_API_KEY is not set."

    llm_client = genai.Client(api_key=api_key)

    # Build model tool declarations (browser_* + finish_*).
    function_decls = list(FN_BROWSER_TOOLS)
    function_decls.append(fn_finish_success())
    function_decls.append(fn_finish_failure())

    last_tool_result = ""
    step = 0

    try:
        async with MCPBrowser(headless=HEADLESS) as browser:
            # Basic sanity: ensure navigate + snapshot exist
            available = await browser.list_tools()
            if "browser_navigate" not in available or "browser_snapshot" not in available:
                return False, "Required MCP tools not available (need browser_navigate and browser_snapshot)."

            while step < MAX_STEPS:
                step += 1
                
                # Add delay between steps to avoid rate limits (free tier: 10 req/min = 1 req per 6 sec)
                if step > 1:
                    await asyncio.sleep(6.5)
                
                snapshot = await browser.call("browser_snapshot", {})
                # keep prompt small
                snapshot = snapshot[-30000:]
                last_tail = last_tool_result[-4000:]

                contents = [
                    {"role": "user", "parts": [
                        genai_types.Part.from_text(USER_PRIMER),
                        genai_types.Part.from_text(json.dumps({
                            "goal": goal,
                            "start_url": start_url,
                            "step": step,
                            "last_tool_result": last_tail,
                            "snapshot": snapshot
                        }, ensure_ascii=False))
                    ]}
                ]

                function_declarations = [genai_types.FunctionDeclaration(**decl) for decl in function_decls]
                
                config = genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(function_declarations=function_declarations)],
                    system_instruction=SYSTEM_INSTRUCTION
                )

                # Retry logic for rate limits
                max_retries = 3
                retry_count = 0
                resp = None
                
                while retry_count < max_retries:
                    try:
                        resp = llm_client.models.generate_content(
                            model=MODEL,
                            contents=contents,
                            config=config
                        )
                        break  # Success, exit retry loop
                    except Exception as e:
                        error_str = str(e)
                        if "429" in error_str or "quota" in error_str.lower():
                            retry_count += 1
                            if retry_count < max_retries:
                                wait_time = 6 * retry_count  # 6, 12, 18 seconds
                                print(f"  Rate limited. Waiting {wait_time}s before retry {retry_count}/{max_retries}...")
                                await asyncio.sleep(wait_time)
                            else:
                                return False, "API rate limit exceeded. Please wait a minute and try again."
                        else:
                            raise  # Re-raise non-rate-limit errors
                
                if not resp:
                    return False, "Failed to get response from API after retries."

                # Find the function call
                fc = None
                try:
                    parts = resp.candidates[0].content.parts
                    for p in parts:
                        if getattr(p, "function_call", None):
                            fc = p.function_call
                            break
                except Exception:
                    pass

                if not fc:
                    return False, "Model did not return a function call."

                name = fc.name
                args = dict(fc.args or {})

                if name == "finish_success":
                    print(f"  → Success: {args.get('message', 'Success.')}")
                    return True, str(args.get("message", "Success."))
                if name == "finish_failure":
                    print(f"  → Failure: {args.get('reason', 'Failed.')}")
                    return False, str(args.get("reason", "Failed."))

                # Guardrail: allow only our minimal set
                allowed = {t["name"] for t in FN_BROWSER_TOOLS}
                if name not in allowed:
                    last_tool_result = f"(Blocked tool {name})"
                    continue

                # Simple loop detection - if same action repeats 3 times, provide guidance
                if step >= 3 and name in ["browser_click", "browser_type"]:
                    recent_actions = []
                    # This is simplified - in production you'd track actual action history
                    # For now, just add helpful context to last_tool_result
                    pass

                # Hint: if model hasn't navigated yet, encourage it by providing start_url
                if name == "browser_navigate" and "url" not in args:
                    args["url"] = start_url

                try:
                    print(f"Step {step}: Calling {name} with {args}")
                    last_tool_result = await browser.call(name, args)
                    
                    # Add hint if they're on inventory page and should go to cart
                    if "inventory.html" in last_tool_result and step > 5:
                        last_tool_result += "\n\nHINT: You've added items. Look for shopping_cart_link or cart badge in the snapshot to view your cart."
                    
                    print(f"  Result: {last_tool_result[:200]}...")
                except Exception as e:
                    # Feed error back to the model; it may recover or finish_failure.
                    last_tool_result = f"(Tool `{name}` error: {e})"
                    print(f"  Error: {e}")

            return False, f"Stopped after {MAX_STEPS} steps without finish_success."

    except Exception as e:
        # Filter out cleanup-related errors
        error_str = str(e)
        if "cancel scope" in error_str.lower() or "taskgroup" in error_str.lower():
            return False, "Browser session ended (cleanup error suppressed)."
        return False, f"Unexpected error: {e}"


def _read_goal() -> str:
    default = "Log in on saucedemo with the standard user and report the price of 'Sauce Labs Backpack'."
    print("Enter a goal (or press Enter to use a small demo goal):")
    g = input("> ").strip()
    return g or default


def main():
    goal = _read_goal()
    try:
        ok, msg = asyncio.run(run_agent(goal=goal, start_url=DEFAULT_START_URL))
        print("\n=== FINAL RESULT ===")
        if ok:
            print(f"SUCCESS: {msg}")
        else:
            print(f"FAILURE: {msg}")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        # Catch any remaining cleanup errors
        error_str = str(e)
        if "cancel scope" not in error_str.lower() and "taskgroup" not in error_str.lower():
            print(f"\n=== ERROR ===")
            print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()