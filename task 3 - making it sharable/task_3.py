from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Initialize FastAPI app
app = FastAPI(
    title="Robot Driver API",
    description="Web automation service for Sauce Demo",
    version="1.0.0"
)

# Request model
class AutomationRequest(BaseModel):
    product_name: str = "Sauce Labs Backpack"
    username: Optional[str] = "standard_user"
    password: Optional[str] = "secret_sauce"
    headless: Optional[bool] = True

# Response model
class AutomationResponse(BaseModel):
    status: str
    message: str
    product_name: str
    price: Optional[str] = None

# Configuration
SAUCE_URL = "https://www.saucedemo.com/"
TIMEOUT_MS = 30_000

# CSS Selectors
SEL_USERNAME = "#user-name"
SEL_PASSWORD = "#password"
SEL_LOGIN_BTN = "#login-button"
SEL_INVENTORY_LIST = ".inventory_list"
SEL_ITEM = ".inventory_item"
SEL_ITEM_NAME = ".inventory_item_name"
SEL_ITEM_PRICE = ".inventory_item_price"


async def run_automation(product_name: str, username: str, password: str, headless: bool) -> AutomationResponse:
    """
    Runs the browser automation asynchronously.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(TIMEOUT_MS)

            # Navigate to login page
            await page.goto(SAUCE_URL, wait_until="domcontentloaded")

            # Perform login
            await page.fill(SEL_USERNAME, username)
            await page.fill(SEL_PASSWORD, password)
            await page.click(SEL_LOGIN_BTN)

            # Wait for inventory page
            await page.locator(SEL_INVENTORY_LIST).wait_for(state="visible", timeout=TIMEOUT_MS)

            # Find product by name
            product_cards = page.locator(SEL_ITEM).filter(
                has=page.locator(SEL_ITEM_NAME, has_text=product_name)
            )

            count = await product_cards.count()
            if count == 0:
                await context.close()
                await browser.close()
                return AutomationResponse(
                    status="failure",
                    message=f"Product '{product_name}' was not found",
                    product_name=product_name
                )

            # Extract price
            price_text = await product_cards.first.locator(SEL_ITEM_PRICE).inner_text(timeout=TIMEOUT_MS)
            price_text = price_text.strip()

            if not price_text:
                await context.close()
                await browser.close()
                return AutomationResponse(
                    status="failure",
                    message=f"Price for '{product_name}' could not be read",
                    product_name=product_name
                )

            await context.close()
            await browser.close()

            return AutomationResponse(
                status="success",
                message=f"Product found successfully",
                product_name=product_name,
                price=price_text
            )

    except PlaywrightTimeoutError:
        return AutomationResponse(
            status="error",
            message="Operation timed out. The page may be slow or elements changed",
            product_name=product_name
        )
    except PlaywrightError as e:
        return AutomationResponse(
            status="error",
            message=f"Browser automation error: {str(e)}",
            product_name=product_name
        )
    except Exception as e:
        import traceback
        error_details = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        return AutomationResponse(
            status="error",
            message=f"Unexpected error: {error_details}\n{traceback.format_exc()}",
            product_name=product_name
        )


# API Endpoints

@app.get("/")
async def root():
    """Welcome endpoint with API information"""
    return {
        "message": "Hello Charles! Hope you consider my application :D ",
        "version": "1.0.0",
        "endpoints": {
            "/": "This welcome message",
            "/health": "Health check endpoint",
            "/run-automation-simple": "GET - Run the automation task (simplified)",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "Robot Driver API"}


@app.get("/run-automation-simple")
async def run_automation_simple(product_name: str = "Sauce Labs Backpack"):
    """
    Simplified GET endpoint for quick testing.
    Example: http://localhost:8000/run-automation-simple?product_name=Sauce%20Labs%20Backpack
    """
    result = await run_automation(
        product_name=product_name,
        username="standard_user",
        password="secret_sauce",
        headless=True
    )
    
    return result