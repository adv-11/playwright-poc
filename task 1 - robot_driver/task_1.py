from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError


# demo creds for sacuce demo

SAUCE_URL = "https://www.saucedemo.com/"
USERNAME = "standard_user"        
PASSWORD = "secret_sauce"         
PRODUCT_NAME = "Sauce Labs Backpack"
TIMEOUT_MS = 30_000               # default step timeout (ms)
HEADLESS = True                   # set to False to watch it run

# css selectors we care about

SEL_USERNAME = "#user-name"
SEL_PASSWORD = "#password"
SEL_LOGIN_BTN = "#login-button"
SEL_INVENTORY_LIST = ".inventory_list"
SEL_ITEM = ".inventory_item"
SEL_ITEM_NAME = ".inventory_item_name"
SEL_ITEM_PRICE = ".inventory_item_price"


def run() -> int:

    """
    Runs the fixed task end-to-end and prints a final result.
    Returns an exit code (0 = success, non-zero = failure).
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_MS)

            # Go to login
            page.goto(SAUCE_URL, wait_until="domcontentloaded")

            # Log in
            page.fill(SEL_USERNAME, USERNAME)
            page.fill(SEL_PASSWORD, PASSWORD)
            page.click(SEL_LOGIN_BTN)

            # Wait for inventory page to load
            page.locator(SEL_INVENTORY_LIST).wait_for(state="visible", timeout=TIMEOUT_MS)

            # Find the product card by name
            product_cards = page.locator(SEL_ITEM).filter(
                has=page.locator(SEL_ITEM_NAME, has_text=PRODUCT_NAME)
            )

            if product_cards.count() == 0:
                print(f"FAILURE: Product '{PRODUCT_NAME}' was not found.")
                context.close()
                browser.close()
                return 1

            # 4) Read its price
            price_text = product_cards.first.locator(SEL_ITEM_PRICE).inner_text(timeout=TIMEOUT_MS).strip()
            if not price_text:
                print(f"FAILURE: Price for '{PRODUCT_NAME}' could not be read.")
                context.close()
                browser.close()
                return 1

            print(f"SUCCESS! Product '{PRODUCT_NAME}' found at price {price_text}")
            context.close()
            browser.close()
            return 0

    except PlaywrightTimeoutError:

        print("A step timed out. The page may be slow or elements changed.")

        return 2
    
    except PlaywrightError as e:

        print(f" Browser automation error: {e}")
        return 2
    
    except Exception as e:

        print(f" error: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())