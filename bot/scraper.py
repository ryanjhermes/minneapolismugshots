"""Nightly scrape of the Hennepin County Jail Roster with Selenium + Chrome.

run() opens the roster, filters to today's bookings, opens each booking's modal and reads name,
charges, severity, bail and the mugshot (FieldExtractor). Anyone with a mugshot is kept. Results
go to jail_roster_data.csv and mugshots/, and the ranked top 10 to posting_queue.json.

The roster is an Angular app that changes without notice, so most lookups try several strategies
and log what they found. When a scrape comes back empty, the CI log shows which step broke.
"""
import base64
import csv
import os
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from . import config, posting_queue, removals
from .common import delete_file, today
from .ranking import most_severe

CSV_FIELDS = ['Full Name', 'Charge 1', 'Severity', 'Bail', 'Mugshot_File']
MODAL_CSS = '[role="dialog"], .modal, [class*="modal"]'
LOG_PREFIX = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️", "DEBUG": "🔍"}


def log(message, level="INFO"):
    print(f"{LOG_PREFIX.get(level, 'ℹ️')} {message}")


def is_ci():
    return bool(os.getenv('CI') or os.getenv('GITHUB_ACTIONS'))


# --- Entry point ---

def run(limit=config.DEFAULT_INMATE_LIMIT):
    """Scrape up to `limit` of today's bookings, save the CSV and mugshots, rebuild the posting queue."""
    driver = open_browser()
    try:
        print("Opening Hennepin County Jail Roster...")
        driver.get(config.JAIL_ROSTER_URL)
        time.sleep(3)
        print(f"Page Title: {driver.title}\nCurrent URL: {driver.current_url}")
        print("⏳ Waiting for page content to fully load...")
        time.sleep(5)  # Angular renders after load
        source = driver.page_source.lower()
        if "server unavailable" in source and "disconnected" in source:
            print("⚠️  Website appears to be unavailable or down")
        else:
            print("✅ Website loaded successfully")
        # Try the form either way: the outage banner sometimes shows on a working page
        scrape_today(driver, limit)
    except Exception as e:
        print(f"❌ Scrape failed: {e}")
    finally:
        driver.quit()
        print("Browser closed.")


def open_browser():
    options = webdriver.ChromeOptions()
    if is_ci():
        print("🤖 Running in CI environment - using headless mode")
        options.add_argument('--headless=new')
        # Headless defaults to 800x600, which renders the booking modal in a narrow
        # layout where charges were never found. Match a desktop window instead.
        options.add_argument('--window-size=1920,1080')
    for arg in ('--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled',
                '--disable-web-security', '--disable-features=VizDisplayCompositor'):
        options.add_argument(arg)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def scrape_today(driver, limit):
    """Filter the roster to today, read up to `limit` bookings, then save the CSV and the queue."""
    date = today()
    print(f"\n🗓️  Filling the search form with today's date (Central): {date}")
    filled_from = set_date_field(driver, date, "minDate")
    filled_to = set_date_field(driver, date, "maxDate")
    if filled_from and filled_to:
        print("✅ Both 'from' and 'to' date fields filled")
    elif filled_from or filled_to:
        print(f"⚠️  Only the '{'from' if filled_from else 'to'}' date field filled")
    else:
        print(f"❌ Failed to fill any date fields with: {date}")

    print("\n🔽 Setting results per page to 100...")
    if select_dropdown_option(driver, "100"):
        print("✅ Successfully set results per page to 100")
    else:
        print("⚠️  Could not set results per page to 100")

    print("\n⏳ Waiting for search results to load...")
    time.sleep(3)
    try:
        inmates = BookingProcessor(driver).process_all(limit)
    except Exception as e:
        print(f"❌ Error processing bookings: {e}")
        inmates = []

    # Never re-publish anyone who asked to be taken down
    removed = removals.load()
    for d in [d for d in inmates if removals.is_removed(d.get('Full Name'), removed)]:
        print("⏭️  Skipping a record on the removal list")
        delete_file(d.get('Mugshot_File', ''), label="mugshot")
        inmates.remove(d)

    if not inmates:
        print("\n❌ No data extracted from booking IDs")
        return
    if not save_csv(inmates):
        print("\n⚠️  Data extracted but failed to save to CSV")
        return
    print(f"\n📊 {len(inmates)} inmates scraped:")
    for i, d in enumerate(inmates, 1):
        print(f"   {i}. {d.get('Full Name', 'N/A')} - {d.get('Charge 1', 'N/A')} - {d.get('Bail', 'N/A')} - Image: {d.get('Mugshot_File', 'N/A')}")
    posting_queue.build(inmates)


# --- Search form ---

def set_date_field(driver, date_value, field="minDate"):
    """Put date_value (MM/DD/YYYY) into the roster's minDate or maxDate input.
    Tries a JavaScript set, then typing, then clicking a date picker. Returns True on success."""
    try:
        print(f"\n📅 Filling '{field}' date field...")
        date_input = _find_date_input(driver, field)
        if not date_input:
            print("❌ Could not find the date input field")
            return False

        driver.execute_script("arguments[0].scrollIntoView(true);", date_input)
        time.sleep(0.5)
        initial = date_input.get_attribute('value')

        def changed():
            value = date_input.get_attribute('value')
            return bool(value) and value != initial

        # The inputs are type="date", which take YYYY-MM-DD
        try:
            month, day, year = date_value.split('/')
            iso_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        except ValueError:
            iso_date = date_value

        # Method 1: set the value with JavaScript and fire the events Angular listens for
        try:
            driver.execute_script("arguments[0].removeAttribute('readonly');", date_input)
            driver.execute_script("arguments[0].removeAttribute('disabled');", date_input)
            date_input.click()
            time.sleep(0.3)
            date_input.clear()
            time.sleep(0.3)
            driver.execute_script("arguments[0].value = '';", date_input)
            time.sleep(0.3)
            driver.execute_script(f"arguments[0].value = '{iso_date}';", date_input)
            for event in ('input', 'change', 'blur'):
                driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{ bubbles: true }}));", date_input)
            time.sleep(1)
            if changed():
                print(f"✅ Set by JavaScript: {date_input.get_attribute('value')}")
                return True
            print("❌ JavaScript set didn't change the value")
        except Exception as e:
            print(f"❌ JavaScript set error: {e}")

        # Method 2: type it one character at a time
        try:
            date_input.click()
            time.sleep(0.3)
            date_input.clear()
            time.sleep(0.2)
            date_input.send_keys(Keys.CONTROL + "a")
            time.sleep(0.2)
            date_input.send_keys(Keys.DELETE)
            time.sleep(0.2)
            for char in iso_date:
                date_input.send_keys(char)
                time.sleep(0.1)
            date_input.send_keys(Keys.TAB)
            time.sleep(1)
            if changed():
                print(f"✅ Set by typing: {date_input.get_attribute('value')}")
                return True
            print("❌ Typing didn't change the value")
        except Exception as e:
            print(f"❌ Typing error: {e}")

        # Method 3: open a date picker if there is one
        for selector in ('button[aria-label*="calendar"]', '[class*="calendar"]', '[class*="date-picker"]',
                         '.mat-datepicker-toggle'):
            try:
                driver.find_element(By.CSS_SELECTOR, selector).click()
                time.sleep(1)
                print(f"✅ Clicked date picker: {selector}")
                return True
            except Exception:
                continue
        print("❌ No date picker found")

        if changed():
            return True
        print("❌ All methods failed - field remains unchanged")
        return False

    except Exception as e:
        print(f"❌ Error inputting date: {e}")
        return False


def _find_date_input(driver, field):
    try:
        return WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f'input[formcontrolname="{field}"]')))
    except Exception:
        pass
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="date"]')
        if inputs:
            # minDate is the first date input, maxDate the second
            return inputs[1] if field == "maxDate" and len(inputs) > 1 else inputs[0]
    except Exception:
        pass
    return None


def select_dropdown_option(driver, option_text="100"):
    """Pick option_text in the results-per-page dropdown. Returns True on success."""
    try:
        dropdown = None
        try:
            for select in driver.find_elements(By.CSS_SELECTOR, 'select'):
                if any(option_text in o.text for o in select.find_elements(By.TAG_NAME, 'option')):
                    dropdown = select
                    break
        except Exception as e:
            print(f"Dropdown search error: {e}")
        if not dropdown:
            try:
                for select in driver.find_elements(By.CSS_SELECTOR, 'select[class*="ng-"], cds-select select, select'):
                    if any(n in select.get_attribute('outerHTML') for n in ['10', '25', '50', '100']):
                        dropdown = select
                        break
            except Exception as e:
                print(f"Dropdown search error: {e}")
        if not dropdown:
            print("❌ Could not find dropdown element")
            return False

        driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
        time.sleep(0.5)

        # Method 1: Selenium's Select, by visible text then by matching text or value
        try:
            select = Select(dropdown)
            try:
                select.select_by_visible_text(option_text)
                return True
            except Exception:
                pass
            try:
                for option in select.options:
                    if option_text in option.text or option_text in option.get_attribute('value'):
                        select.select_by_value(option.get_attribute('value'))
                        return True
            except Exception:
                pass
        except Exception as e:
            print(f"Select error: {e}")

        # Method 2: click the dropdown, then the option
        try:
            dropdown.click()
            time.sleep(1)
            for option in dropdown.find_elements(By.TAG_NAME, 'option'):
                if option_text in option.text:
                    option.click()
                    time.sleep(0.5)
                    return True
        except Exception as e:
            print(f"Click error: {e}")

        # Method 3: set the value with JavaScript
        try:
            target = next((o.get_attribute('value') for o in dropdown.find_elements(By.TAG_NAME, 'option')
                           if option_text in o.text), None)
            if target:
                driver.execute_script(f"arguments[0].value = '{target}';", dropdown)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", dropdown)
                return True
        except Exception as e:
            print(f"JavaScript select error: {e}")

        print("❌ All dropdown selection methods failed")
        return False

    except Exception as e:
        print(f"❌ Error selecting dropdown option: {e}")
        return False


# --- Bookings ---

class BookingProcessor:
    """Finds booking IDs in the results table and reads each booking's modal."""

    def __init__(self, driver):
        self.driver = driver
        self.extractor = FieldExtractor(driver)

    def find_booking_ids(self, limit):
        """Clickable elements whose text looks like a booking number (8-12 digits)."""
        print(f"\n🔍 Looking for booking IDs (limit: {limit})...")
        found = []
        for element in self.driver.find_elements(By.CSS_SELECTOR, 'a, button[onclick], [role="button"], cds-button'):
            text = element.text.strip()
            if text and text.isdigit() and 8 <= len(text) <= 12 and int(text) > 10000000:
                found.append({'element': element, 'id': text})
                print(f"📋 Found booking ID: {text}")
                if len(found) >= limit:
                    break
        print(f"✅ Found {len(found)} booking IDs")
        return found

    def process_booking(self, booking, index, total):
        """Open one booking's modal and read it. Returns the data dict, or None on error."""
        print(f"\n{'=' * 50}\n🔄 Processing booking {index + 1}/{total}: {booking['id']}\n{'=' * 50}")
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", booking['element'])
            time.sleep(1)
            print(f"🖱️  Clicking booking ID: {booking['id']}")
            booking['element'].click()
            time.sleep(config.CLICK_WAIT_TIME)

            data = self.extractor.extract_all_fields()
            has_charge = data['Charge 1'] != 'No charge listed'
            has_bail = data['Bail'] != 'No bail information'
            print(f"📊 Charge: {'✅' if has_charge else '❌'}, Bail: {'✅' if has_bail else '❌'}")
            # A booking without a readable name is still usable: name it after the booking number
            if data['Full Name'] == 'Unknown':
                data['Full Name'] = f"Booking_{booking['id']}"
                print(f"⚠️  Using booking ID as fallback name: {data['Full Name']}")
            return data
        except Exception as e:
            print(f"❌ Error processing booking {booking['id']}: {e}")
            return None

    def process_all(self, limit):
        """Read up to `limit` bookings and return the ones with a mugshot."""
        bookings = self.find_booking_ids(limit)
        if not bookings:
            print("❌ No booking IDs found")
            return []

        accepted = []
        for n, booking in enumerate(bookings):
            data = self.process_booking(booking, n, len(bookings))
            if data:
                if data.get('Mugshot_File') and data['Mugshot_File'] != 'No Image':
                    accepted.append(data)
                    print(f"✅ ACCEPTED: {data['Full Name']}")
                else:
                    print(f"⏭️  REJECTED: {data['Full Name']} - Missing mugshot")
            # Hide the modal so the next booking ID can be clicked (raises if no modal is found)
            modal = self.driver.find_element(By.CSS_SELECTOR, MODAL_CSS)
            self.driver.execute_script("arguments[0].style.display = 'none';", modal)
            time.sleep(1)

        print(f"\n📊 PROCESSING SUMMARY: {len(bookings)} processed, {len(accepted)} accepted, "
              f"{len(bookings) - len(accepted)} rejected")
        return accepted


class FieldExtractor:
    """Reads one open booking modal into {Full Name, Charge 1, Bail, Mugshot_File, Severity}.

    Missing fields get placeholders ('Unknown', 'No charge listed', 'No bail information',
    'No Image'). Severity is only set when a charge is found."""

    def __init__(self, driver):
        self.driver = driver
        self.data = {}

    def extract_all_fields(self):
        log("Starting field extraction...", "INFO")
        self.data = {'Full Name': '', 'Charge 1': '', 'Bail': '', 'Mugshot_File': 'No Image'}
        self._wait_for_charges()

        page_text = self._get_page_text()
        self._extract_name(page_text)
        self._extract_charge(page_text)
        if not self.data['Charge 1']:
            log("Charge missing after first pass - waiting and retrying", "WARNING")
            time.sleep(3)
            page_text = self._get_page_text()
            self._extract_charge(page_text)
        self._extract_bail(page_text)
        self._extract_mugshot()

        self.data['Full Name'] = self.data['Full Name'] or 'Unknown'
        self.data['Charge 1'] = self.data['Charge 1'] or 'No charge listed'
        self.data['Bail'] = self.data['Bail'] or 'No bail information'
        log("=== EXTRACTION SUMMARY ===", "INFO")
        for key, value in self.data.items():
            log(f"{key}: {value}", "INFO")
        return self.data

    # Modal access

    def _find_modal(self):
        for selector in config.MODAL_SELECTORS:
            try:
                modal = self.driver.find_element(By.CSS_SELECTOR, selector)
                if modal.is_displayed():
                    return modal
            except Exception:
                continue
        return None

    def _get_page_text(self):
        modal = self._find_modal()
        if modal and modal.text.strip():
            return modal.text
        return self.driver.find_element(By.TAG_NAME, 'body').text

    def _wait_for_charges(self):
        """Wait until the modal's charge section has rendered (it loads after the rest)."""
        timeout = config.MODAL_CHARGE_WAIT_TIMEOUT_CI if is_ci() else config.MODAL_CHARGE_WAIT_TIMEOUT
        try:
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, MODAL_CSS)))
        except TimeoutException:
            log("Modal container not found within timeout", "WARNING")
            time.sleep(config.MODAL_WAIT_TIME)
            return

        def charges_loaded(_driver):
            text = self._get_page_text()
            return 'Charge: 1' in text and 'Description:' in text

        try:
            WebDriverWait(self.driver, timeout).until(charges_loaded)
            log("Charge section loaded in modal", "SUCCESS")
            return
        except TimeoutException:
            log(f"Charge section not ready after {timeout}s - scrolling modal and retrying", "WARNING")

        modal = self._find_modal()
        if modal:
            try:
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", modal)
                time.sleep(2)
                WebDriverWait(self.driver, 5).until(charges_loaded)
                log("Charge section loaded after scrolling modal", "SUCCESS")
                return
            except TimeoutException:
                pass
        time.sleep(config.MODAL_WAIT_TIME)

    # Name

    def _extract_name(self, page_text):
        """The line after a name label, if it looks like a full name."""
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            for pattern in config.NAME_PATTERNS:
                if pattern in line.strip() and i + 1 < len(lines):
                    name = lines[i + 1].strip()
                    if self._is_valid_name(name):
                        self.data['Full Name'] = name
                        log(f"Found name: {name}", "SUCCESS")
                        return
        log("No valid name found", "WARNING")

    @staticmethod
    def _is_valid_name(name):
        return (bool(name) and config.MIN_NAME_LENGTH <= len(name) <= config.MAX_NAME_LENGTH
                and ' ' in name and any(c.isalpha() for c in name))

    # Charges and severity

    def _extract_charge(self, page_text):
        """Charges from the visible text, else from the DOM of the current modal only.
        Also sets Severity from the 'Severity of Charge:' fields plus keywords in the charges."""
        charges = self._clean_charges(self._charges_from_text(page_text))
        source = "text"
        if not charges:
            modal = self._find_modal()
            # Only trust the DOM if this modal belongs to the inmate we just named,
            # so a stale modal can never attach someone else's charge.
            name = self.data['Full Name']
            if modal and name and name in (modal.get_attribute('textContent') or ''):
                charges = self._clean_charges(self._charges_from_dom(modal))
                source = "DOM"

        if not charges:
            log("No valid charge found", "WARNING")
            # Leave evidence in the CI log so a future layout change is quick to diagnose
            log(f"Modal text sample: {page_text[:1500]!r}", "DEBUG")
            return

        self.data['Charge 1'] = config.CHARGE_SEPARATOR.join(charges)
        lines = [l.strip() for l in page_text.split('\n')]
        severities = [
            (l[len('Severity of Charge:'):].strip() or (lines[i + 1] if i + 1 < len(lines) else ''))
            for i, l in enumerate(lines) if l.startswith('Severity of Charge:')
        ]
        self.data['Severity'] = most_severe(severities + charges)
        log(f"Found charge ({source}): {self.data['Charge 1']}", "SUCCESS")

    @staticmethod
    def _charges_from_text(page_text):
        """Every 'Description:' value, whether it sits on the same line or the next one."""
        lines = [l.strip() for l in page_text.split('\n')]
        charges = []
        for i, line in enumerate(lines):
            if line.startswith('Description:'):
                value = line[len('Description:'):].strip()
                if not value and i + 1 < len(lines):
                    value = lines[i + 1]
                charges.append(value)
        return charges

    def _charges_from_dom(self, modal):
        """'Description:' values read from the DOM's textContent, so a narrow or collapsed
        layout that hides text from Selenium's .text can't hide the charge."""
        try:
            return self.driver.execute_script("""
                const out = [];
                for (const el of arguments[0].querySelectorAll('*')) {
                    if (el.children.length || el.textContent.trim() !== 'Description:') continue;
                    let val = el.nextElementSibling ? el.nextElementSibling.textContent : '';
                    if (!val.trim() && el.parentElement) {
                        val = el.parentElement.textContent.replace('Description:', '');
                    }
                    out.push(val.trim());
                }
                return out;
            """, modal) or []
        except Exception as e:
            log(f"DOM charge extraction failed: {e}", "DEBUG")
            return []

    @staticmethod
    def _clean_charges(charges):
        """Valid charges only, de-duplicated, in order, at most config.MAX_CHARGES."""
        seen, result = set(), []
        for c in charges:
            c = ' '.join((c or '').split())
            if FieldExtractor._is_valid_charge(c) and c.upper() not in seen:
                seen.add(c.upper())
                result.append(c)
        return result[:config.MAX_CHARGES]

    @staticmethod
    def _is_valid_charge(charge):
        return (bool(charge) and config.MIN_CHARGE_LENGTH <= len(charge) <= config.MAX_CHARGE_LENGTH
                and not charge.endswith(':') and charge not in config.INVALID_CHARGES)

    # Bail

    def _extract_bail(self, page_text):
        """The line after 'Bail Options:', or the value after 'Bail:' on the same line."""
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if 'Bail Options:' in line and i + 1 < len(lines):
                value = lines[i + 1].strip()
            elif 'Bail:' in line:
                value = line.split(":", 1)[1].strip()
            else:
                continue
            if self._is_valid_bail(value):
                self.data['Bail'] = value
                log(f"Found bail: {value}", "SUCCESS")
                return
        log("No valid bail information found", "WARNING")

    @staticmethod
    def _is_valid_bail(bail):
        if not bail or not bail.strip():
            return False
        upper = bail.upper()
        if not ('$' in bail or 'NO BAIL' in upper or 'RELEASED' in upper or 'BOND' in upper):
            return False
        return not any(bail.strip().upper() == p.upper() for p in config.INVALID_BAILS)

    # Mugshot

    def _extract_mugshot(self):
        """Save the first image that looks like a booking photo to mugshots/mugshot_<NAME>.jpg."""
        try:
            for img in self.driver.find_elements(By.CSS_SELECTOR, 'img'):
                src = img.get_attribute('src')
                alt = (img.get_attribute('alt') or "").lower()
                if not src or not ('data:image' in src or 'booking' in alt or 'photo' in alt or 'mugshot' in alt):
                    continue
                if self.data['Full Name']:
                    clean = "".join(c for c in self.data['Full Name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    prefix = f"mugshot_{clean.replace(' ', '_')}"
                else:
                    prefix = f"mugshot_{int(time.time())}"
                path = save_mugshot(src, prefix)
                if path:
                    self.data['Mugshot_File'] = path
                    return
            log("No mugshot image found", "WARNING")
        except Exception as e:
            log(f"Error extracting mugshot: {e}", "ERROR")


# --- Files ---

def save_mugshot(data_url, filename_prefix):
    """Decode a base64 data URL into mugshots/<prefix>.jpg (or .png). Returns the path, or None."""
    try:
        os.makedirs(config.MUGSHOTS_DIR, exist_ok=True)
        header, encoded = data_url.split(',', 1) if ',' in data_url else ("", data_url)
        ext = "png" if "png" in header and not ("jpeg" in header or "jpg" in header) else "jpg"
        path = os.path.join(config.MUGSHOTS_DIR, f"{filename_prefix}.{ext}")
        with open(path, "wb") as f:
            f.write(base64.b64decode(encoded))
        print(f"✅ Saved mugshot image: {path}")
        return path
    except Exception as e:
        print(f"❌ Error converting image: {e}")
        return None


def save_csv(inmates):
    """Overwrite jail_roster_data.csv with this scrape. Returns True on success."""
    try:
        with open(config.CSV_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(inmates)
        print(f"✅ Saved {len(inmates)} records to {config.CSV_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")
        return False
