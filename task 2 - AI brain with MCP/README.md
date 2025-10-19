# AI Brain with MCP : Task automation with google gemini and playwright mcp

A simple web automation agent that uses Google's Gemini AI to navigate websites and complete tasks autonomously using the Model Context Protocol (MCP) with Playwright.

## Output Screenshots

![Output Example 1](output_screenshots/output_1.png)

![Output Example 2](output_screenshots/output_2.png)

## Overview

This agent can:

- Navigate websites automatically
- Fill forms and click buttons
- Complete multi-step workflows (e.g., login, add to cart, checkout)
- Extract information from pages
- Make decisions based on page content

The agent uses Gemini 2.5 Flash as the reasoning engine and Playwright (via MCP) for browser automation.

## How It Works

1. **Agent receives a goal** - User provides a task description (e.g., "Log in and find product price")
2. **Take snapshot** - Browser captures accessibility snapshot with element references
3. **Gemini analyzes** - AI model examines snapshot and decides next action
4. **Execute action** - Calls appropriate browser tool (navigate, click, type, etc.)
5. **Repeat** - Continues until goal is achieved or max steps reached

## Prerequisites

- Python 3.8+
- Node.js and npm (for Playwright MCP server)
- Google Gemini API key

## Installation

1. Install Python dependencies:

```bash
pip install mcp google-genai python-dotenv
```

2. Install Playwright MCP server:

```bash
npm install -g @playwright/mcp
```

3. Create `.env` file with your API key:

```
GEMINI_API_KEY=your_api_key_here
```

## Usage

Run the script:

```bash
python main.py
```

You'll be prompted to enter a goal. Press Enter to use the default demo goal, or type your own:

```
Enter a goal (or press Enter to use a small demo goal):
> Log in on saucedemo with the standard user and report the price of 'Sauce Labs Backpack'.
```

### Example Goals

- "Log in and report the price of Sauce Labs Backpack"
- "Add two items to cart and tell me the total"
- "Navigate to the about page and summarize the content"


## Notes

- Free tier Gemini API has rate limits (10 req/min)
- Agent includes automatic retry logic for rate limits
- Default timeout is 15 steps to prevent infinite loops
- Works best with structured websites that have good accessibility markup
