# Essential imports for all functions
import time
from datetime import datetime, timedelta
import csv
import base64
import os
import requests
import json
from dotenv import load_dotenv
import re
import pytz

# Load environment variables from .env file (if it exists)
load_dotenv()


class Config:
    """Centralized configuration for the scraping application"""
    
    # Scraping settings
    DEFAULT_INMATE_LIMIT = 100
    TEST_INMATE_LIMIT = 25
    MODAL_WAIT_TIME = 5
    MODAL_CHARGE_WAIT_TIMEOUT = 10
    MODAL_CHARGE_WAIT_TIMEOUT_CI = 25
    CLICK_WAIT_TIME = 3
    
    # Posting limits and scheduling
    # Central Time hours to post one inmate each (peak Instagram hours), then the Top 5 recap reel
    POSTING_HOURS = [7, 9, 11, 12, 13, 17, 19, 20]
    RECAP_HOUR = 21
    PAGES_URL = "https://ryanjhermes.github.io/minneapolismugshots"
    DISCLAIMER = "Charges are allegations, not convictions. All persons are presumed innocent until proven guilty in a court of law."
    REELS_DIR = "reels"
    
    # Quality thresholds
    MIN_NAME_LENGTH = 3
    MAX_NAME_LENGTH = 50
    MIN_CHARGE_LENGTH = 5
    MAX_CHARGE_LENGTH = 150
    MAX_CHARGES = 3
    CHARGE_SEPARATOR = '; '

    # Ranking bonus added to the 0..1 distinctiveness score, by most severe charge
    SEVERITY_BONUS = {'Felony': 0.2, 'Gross Misdemeanor': 0.1, 'Misdemeanor': 0.0, '': 0.0}
    
    # File paths
    CSV_FILENAME = "jail_roster_data.csv"
    QUEUE_FILENAME = "posting_queue.json"
    MUGSHOTS_DIR = "mugshots"
    
    # Website settings
    JAIL_ROSTER_URL = "https://jailroster.hennepin.us/"
    
    # Date format
    DATE_FORMAT = "%m/%d/%Y"
    HTML5_DATE_FORMAT = "%Y-%m-%d"
    
    # Invalid patterns for filtering
    INVALID_CHARGES = [
        'No charge listed',
        'Charge information not available',
        'Severity of Charge:',
        'Description:',
        'Charge Status:'
    ]
    
    INVALID_BAILS = [
        'NO BAIL INFORMATION',
        'NO BAIL REQUIRED',
        'No bail information',
        'No bail',
        'No Bail',
        'No bail required',
    ]
    
    # Name patterns for extraction
    NAME_PATTERNS = [
        'Full Name:',
        'Name:',
        'Inmate Name:',
        'Arrestee Name:',
        'Defendant Name:',
        'Subject Name:'
    ]
    
    # CSS selectors
    BOOKING_SELECTORS = [
        'a[href*="booking"]',
        'button[class*="booking"]',
        'td a',
        '[class*="booking-number"] a',
        'a[href*="detail"]',
        '.booking-id a',
    ]
    
    MODAL_SELECTORS = [
        '[role="dialog"]',
        '.modal',
        '[class*="modal"]',
        '[class*="dialog"]'
    ]

def classify_severity(text):
    """Map severity text or charge text to Felony / Gross Misdemeanor / Misdemeanor / ''."""
    t = (text or '').upper()
    if 'FELONY' in t:
        return 'Felony'
    if 'GROSS' in t or re.search(r'\bGM\b', t):
        return 'Gross Misdemeanor'
    if 'MISD' in t:
        return 'Misdemeanor'
    return ''

def most_severe(values):
    order = ['', 'Misdemeanor', 'Gross Misdemeanor', 'Felony']
    return max((classify_severity(v) for v in values), key=order.index, default='')

class FieldExtractor:
    """Dedicated class for extracting inmate data fields with better debugging"""
    
    def __init__(self, driver):
        self.driver = driver
        self.debug_mode = True
        self.extracted_data = {
            'Full Name': '',
            'Charge 1': '',
            'Bail': '',
            'Mugshot_File': 'No Image'
        }
    
    def log(self, message, level="INFO"):
        """Centralized logging with levels"""
        if self.debug_mode:
            prefix = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️", "DEBUG": "🔍"}
            print(f"{prefix.get(level, 'ℹ️')} {message}")
    
    def _modal_charge_wait_timeout(self):
        is_ci = os.getenv('CI') or os.getenv('GITHUB_ACTIONS')
        return Config.MODAL_CHARGE_WAIT_TIMEOUT_CI if is_ci else Config.MODAL_CHARGE_WAIT_TIMEOUT

    def _find_modal_element(self):
        from selenium.webdriver.common.by import By

        for selector in Config.MODAL_SELECTORS:
            try:
                modal = self.driver.find_element(By.CSS_SELECTOR, selector)
                if modal.is_displayed():
                    return modal
            except Exception:
                continue
        return None

    def _get_page_text(self):
        from selenium.webdriver.common.by import By

        modal = self._find_modal_element()
        if modal and modal.text.strip():
            return modal.text
        return self.driver.find_element(By.TAG_NAME, 'body').text

    def _wait_for_modal_charge_content(self):
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        timeout = self._modal_charge_wait_timeout()

        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[role="dialog"], .modal, [class*="modal"]'))
            )
        except TimeoutException:
            self.log("Modal container not found within timeout", "WARNING")
            time.sleep(Config.MODAL_WAIT_TIME)
            return

        def charge_section_loaded(_driver):
            text = self._get_page_text()
            return 'Charge: 1' in text and 'Description:' in text

        try:
            WebDriverWait(self.driver, timeout).until(charge_section_loaded)
            self.log("Charge section loaded in modal", "SUCCESS")
            return
        except TimeoutException:
            self.log(
                f"Charge section not ready after {timeout}s - scrolling modal and retrying",
                "WARNING",
            )

        modal = self._find_modal_element()
        if modal:
            try:
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight;",
                    modal,
                )
                time.sleep(2)
                WebDriverWait(self.driver, 5).until(charge_section_loaded)
                self.log("Charge section loaded after scrolling modal", "SUCCESS")
                return
            except TimeoutException:
                pass

        time.sleep(Config.MODAL_WAIT_TIME)

    def extract_all_fields(self):
        """Main extraction method that orchestrates all field extraction"""
        self.log("Starting field extraction...", "INFO")
        
        # Reset extracted data for each new inmate
        self.extracted_data = {
            'Full Name': '',
            'Charge 1': '',
            'Bail': '',
            'Mugshot_File': 'No Image'
        }
        
        self._wait_for_modal_charge_content()
        
        page_text = self._get_page_text()
        self.log(f"Page content length: {len(page_text)} characters", "DEBUG")
        
        # Extract each field
        self._extract_name(page_text)
        self._extract_charge(page_text)

        if not self.extracted_data['Charge 1']:
            self.log("Charge missing after first pass - waiting and retrying", "WARNING")
            time.sleep(3)
            page_text = self._get_page_text()
            self.log(f"Retry page content length: {len(page_text)} characters", "DEBUG")
            self._extract_charge(page_text)
            if not self.extracted_data['Bail']:
                self._extract_bail(page_text)

        self._extract_bail(page_text)
        self._extract_mugshot()
        
        # Set defaults for missing fields
        self._set_defaults()
        
        # Log final results
        self._log_extraction_summary()
        
        return self.extracted_data
    
    def _extract_name(self, page_text):
        """Extract full name using multiple strategies"""
        self.log("Extracting full name...", "DEBUG")
        
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            for pattern in Config.NAME_PATTERNS:
                if pattern in line and i + 1 < len(lines):
                    potential_name = lines[i + 1].strip()
                    if self._is_valid_name(potential_name):
                        self.extracted_data['Full Name'] = potential_name
                        self.log(f"Found name: {potential_name}", "SUCCESS")
                        return
        
        self.log("No valid name found", "WARNING")
    
    def _is_valid_name(self, name):
        """Validate if a string looks like a real name"""
        if not name or len(name) < Config.MIN_NAME_LENGTH:
            return False
        
        # Must contain at least one space (first and last name)
        if ' ' not in name:
            return False
        
        # Must contain alphabetic characters
        if not any(c.isalpha() for c in name):
            return False
        
        # Must be reasonable length
        if len(name) > Config.MAX_NAME_LENGTH:
            return False
        
        return True
    
    def _extract_charges_from_text(self, page_text):
        """Find every 'Description:' value, whether it sits on the same line or the next one."""
        lines = [l.strip() for l in page_text.split('\n')]
        charges = []
        for i, line in enumerate(lines):
            if not line.startswith('Description:'):
                continue
            value = line[len('Description:'):].strip()
            if not value and i + 1 < len(lines):
                value = lines[i + 1]
            charges.append(value)
        return charges

    def _extract_charges_from_dom(self, modal):
        """Read 'Description:' values straight from the DOM via textContent, so a narrow
        or collapsed layout that hides text from Selenium's .text can't hide the charge."""
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
            self.log(f"DOM charge extraction failed: {e}", "DEBUG")
            return []

    def _clean_charges(self, charges):
        """Validate, de-duplicate, keep order, cap at MAX_CHARGES."""
        seen, result = set(), []
        for c in charges:
            c = ' '.join((c or '').split())
            if self._is_valid_charge(c) and c.upper() not in seen:
                seen.add(c.upper())
                result.append(c)
        return result[:Config.MAX_CHARGES]

    def _extract_charge(self, page_text):
        """Extract charges: visible text first, then the DOM of the current modal only"""
        self.log("Extracting charge information...", "DEBUG")

        charges = self._clean_charges(self._extract_charges_from_text(page_text))
        source = "text"

        if not charges:
            modal = self._find_modal_element()
            # Only trust the DOM if this modal belongs to the inmate we just named,
            # so a stale modal can never attach someone else's charge.
            name = self.extracted_data['Full Name']
            if modal and name and name in (modal.get_attribute('textContent') or ''):
                charges = self._clean_charges(self._extract_charges_from_dom(modal))
                source = "DOM"

        if charges:
            self.extracted_data['Charge 1'] = Config.CHARGE_SEPARATOR.join(charges)
            # Severity field values next to each charge, plus keywords in the charge text itself
            lines = [l.strip() for l in page_text.split('\n')]
            severities = [
                (l[len('Severity of Charge:'):].strip() or (lines[i + 1] if i + 1 < len(lines) else ''))
                for i, l in enumerate(lines) if l.startswith('Severity of Charge:')
            ]
            self.extracted_data['Severity'] = most_severe(severities + charges)
            self.log(f"Found charge ({source}): {self.extracted_data['Charge 1']}", "SUCCESS")
            return

        self.log("No valid charge found", "WARNING")
        # Leave evidence in the CI log so a future layout change is quick to diagnose
        self.log(f"Modal text sample: {page_text[:1500]!r}", "DEBUG")

    def _is_valid_charge(self, charge):
        """Validate if a string looks like a real charge"""
        if not charge or len(charge) < Config.MIN_CHARGE_LENGTH:
            return False
        
        # Must not end with colon
        if charge.endswith(':'):
            return False
        
        # Must not be just a label
        if charge in Config.INVALID_CHARGES:
            return False

        # Guard against grabbing a whole block of page text
        if len(charge) > Config.MAX_CHARGE_LENGTH:
            return False
        
        return True
    
    def _extract_bail(self, page_text):
        """Extract bail information using multiple strategies"""
        self.log("Extracting bail information...", "DEBUG")
        
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for bail patterns
            if 'Bail Options:' in line and i + 1 < len(lines):
                bail_value = lines[i + 1].strip()
                if self._is_valid_bail(bail_value):
                    self.extracted_data['Bail'] = bail_value
                    self.log(f"Found bail: {bail_value}", "SUCCESS")
                    return
            
            elif 'Bail:' in line and ':' in line:
                try:
                    bail_label, bail_value = line.split(":", 1)
                    if self._is_valid_bail(bail_value.strip()):
                        self.extracted_data['Bail'] = bail_value.strip()
                        self.log(f"Found bail: {bail_value.strip()}", "SUCCESS")
                        return
                except:
                    continue
        
        self.log("No valid bail information found", "WARNING")
    
    def _is_valid_bail(self, bail):
        """Validate if a string looks like real bail information"""
        if not bail or not bail.strip():
            return False
        
        bail_upper = bail.upper()
        
        # Must contain dollar sign or specific bail keywords
        if not ('$' in bail or 
                'NO BAIL' in bail_upper or
                'RELEASED' in bail_upper or
                'BOND' in bail_upper):
            return False
        
        # Reject invalid patterns
        if any(bail.strip().upper() == pattern.upper() for pattern in Config.INVALID_BAILS):
            return False
        
        return True
    
    def _extract_mugshot(self):
        """Extract and save mugshot image"""
        # Import selenium components needed for this method
        from selenium.webdriver.common.by import By
        
        self.log("Looking for mugshot image...", "DEBUG")
        
        try:
            img_elements = self.driver.find_elements(By.CSS_SELECTOR, 'img')
            self.log(f"Found {len(img_elements)} image elements", "DEBUG")
            
            for img in img_elements:
                src = img.get_attribute('src')
                alt = img.get_attribute('alt') or ""
                
                # Check if this looks like a booking photo
                if (src and 
                    ('data:image' in src or 
                     'booking' in alt.lower() or 
                     'photo' in alt.lower() or 
                     'mugshot' in alt.lower())):
                    
                    self.log(f"Found potential mugshot: {alt}", "DEBUG")
                    
                    # Generate filename
                    if self.extracted_data['Full Name']:
                        clean_name = "".join(c for c in self.extracted_data['Full Name'] 
                                           if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        clean_name = clean_name.replace(' ', '_')
                        filename_prefix = f"mugshot_{clean_name}"
                    else:
                        filename_prefix = f"mugshot_{int(time.time())}"
                    
                    # Save the image
                    saved_filename = convert_base64_to_image(src, filename_prefix)
                    if saved_filename:
                        self.extracted_data['Mugshot_File'] = saved_filename
                        self.log(f"Saved mugshot: {saved_filename}", "SUCCESS")
                        return
            
            self.log("No mugshot image found", "WARNING")
            
        except Exception as e:
            self.log(f"Error extracting mugshot: {e}", "ERROR")
    
    def _set_defaults(self):
        """Set default values for missing fields"""
        if not self.extracted_data['Full Name']:
            self.extracted_data['Full Name'] = 'Unknown'
        if not self.extracted_data['Charge 1']:
            self.extracted_data['Charge 1'] = 'No charge listed'
        if not self.extracted_data['Bail']:
            self.extracted_data['Bail'] = 'No bail information'
    
    def _log_extraction_summary(self):
        """Log a summary of all extracted data"""
        self.log("=== EXTRACTION SUMMARY ===", "INFO")
        for key, value in self.extracted_data.items():
            self.log(f"{key}: {value}", "INFO")

class DataValidator:
    """Validates extracted inmate data for quality control"""
    
    @staticmethod
    def validate_inmate_data(data):
        """Validate if inmate data meets basic requirements (mugshot + name required)"""
        issues = []
        
        # Check name (REQUIRED)
        if not data.get('Full Name') or data['Full Name'] == 'Unknown':
            issues.append("Missing or invalid name")
        
        # Check mugshot (REQUIRED)
        if not data.get('Mugshot_File') or data['Mugshot_File'] == 'No Image':
            issues.append("Missing mugshot")
        
        # Charge and bail are OPTIONAL - don't add to issues
        has_charge = data.get('Charge 1') and data['Charge 1'] != 'No charge listed'
        has_bail = data.get('Bail') and data['Bail'] != 'No bail information'
        
        return len(issues) == 0, issues, has_charge, has_bail
    
    @staticmethod
    def get_posting_priority(data):
        """Calculate posting priority based on optional fields (charge + bail)"""
        priority = 0
        
        # Charge: +1 priority point
        if data.get('Charge 1') and data['Charge 1'] != 'No charge listed':
            priority += 1
        
        # Bail: +1 priority point  
        if data.get('Bail') and data['Bail'] != 'No bail information':
            priority += 1
        
        return priority

class BookingProcessor:
    """Handles booking ID processing with better debugging"""
    
    def __init__(self, driver):
        self.driver = driver
        self.extractor = FieldExtractor(driver)
        self.validator = DataValidator()
    
    def find_booking_ids(self, limit=10):
        """Find clickable booking IDs on the page"""
        # Import selenium components needed for this method
        from selenium.webdriver.common.by import By
        
        print(f"\n🔍 Looking for booking IDs (limit: {limit})...")
        
        booking_ids = []
        all_clickable = self.driver.find_elements(By.CSS_SELECTOR, 'a, button[onclick], [role="button"], cds-button')
        
        for element in all_clickable:
            text = element.text.strip()
            if (text and text.isdigit() and len(text) >= 8 and len(text) <= 12 and int(text) > 10000000):
                booking_ids.append({
                    'element': element,
                    'id': text
                })
                print(f"📋 Found booking ID: {text}")
                
                if len(booking_ids) >= limit:
                    break
        
        print(f"✅ Found {len(booking_ids)} booking IDs")
        return booking_ids
    
    def process_booking(self, booking_info, index, total):
        """Process a single booking ID and extract data"""
        booking_element = booking_info['element']
        booking_id = booking_info['id']
        
        print(f"\n{'='*50}")
        print(f"🔄 Processing booking {index+1}/{total}: {booking_id}")
        print(f"{'='*50}")
        
        try:
            # Scroll to element and highlight
            self.driver.execute_script("arguments[0].scrollIntoView(true);", booking_element)
            time.sleep(0.5)
            
            # Highlight briefly
            try:
                self.driver.execute_script("arguments[0].style.border='3px solid blue';", booking_element)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].style.border='';", booking_element)
            except:
                pass
            
            # Click the booking ID
            print(f"🖱️  Clicking booking ID: {booking_id}")
            booking_element.click()
            time.sleep(Config.CLICK_WAIT_TIME)
            
            # Extract data using FieldExtractor
            extracted_data = self.extractor.extract_all_fields()
            
            # Validate data quality (mugshot + name required)
            is_valid, issues, has_charge, has_bail = self.validator.validate_inmate_data(extracted_data)
            priority = self.validator.get_posting_priority(extracted_data)
            
            print(f"📊 Posting Priority: {priority}/2 (Charge: {'✅' if has_charge else '❌'}, Bail: {'✅' if has_bail else '❌'})")
            if not is_valid:
                print(f"⚠️  Validation Issues: {', '.join(issues)}")
            
            # Use booking ID as fallback name if needed
            if not extracted_data['Full Name'] or extracted_data['Full Name'] == 'Unknown':
                extracted_data['Full Name'] = f"Booking_{booking_id}"
                print(f"⚠️  Using booking ID as fallback name: {extracted_data['Full Name']}")
            
            return extracted_data, priority
            
        except Exception as e:
            print(f"❌ Error processing booking {booking_id}: {e}")
            return None, 0
    
    def process_multiple_bookings(self, limit=10):
        """Process multiple booking IDs with basic filtering (mugshot + name required)"""
        print(f"\n🚀 Starting batch processing (limit: {limit})...")
        
        # Find booking IDs
        booking_ids = self.find_booking_ids(limit)
        
        if not booking_ids:
            print("❌ No booking IDs found")
            return []
        
        all_extracted_data = []
        priorities = []
        
        for i, booking_info in enumerate(booking_ids):
            extracted_data, priority = self.process_booking(booking_info, i, len(booking_ids))
            
            if extracted_data:
                # Only accept inmates with mugshot + name (basic requirements)
                is_valid, issues, _, _ = self.validator.validate_inmate_data(extracted_data)
                if is_valid:
                    all_extracted_data.append(extracted_data)
                    priorities.append(priority)
                    print(f"✅ ACCEPTED: {extracted_data['Full Name']} (Priority: {priority}/2)")
                else:
                    print(f"⏭️  REJECTED: {extracted_data['Full Name']} - Missing: {', '.join(issues)}")
            
            # Close modal
            # Import selenium components needed for modal closing
            from selenium.webdriver.common.by import By
            modal = self.driver.find_element(By.CSS_SELECTOR, '[role="dialog"], .modal, [class*="modal"]')
            self.driver.execute_script("arguments[0].style.display = 'none';", modal)
            time.sleep(1)
        
        # Print summary
        print(f"\n📊 PROCESSING SUMMARY:")
        print(f"   Total IDs processed: {len(booking_ids)}")
        print(f"   Accepted inmates: {len(all_extracted_data)}")
        print(f"   Rejected inmates: {len(booking_ids) - len(all_extracted_data)}")
        if priorities:
            print(f"   Average priority: {sum(priorities)/len(priorities):.1f}/2")
        
        return all_extracted_data

def convert_base64_to_image(data_url, filename_prefix="mugshot"):
    """Convert base64 data URL to an actual image file in mugshots folder"""
    try:
        # Create mugshots directory if it doesn't exist
        mugshots_dir = Config.MUGSHOTS_DIR
        if not os.path.exists(mugshots_dir):
            os.makedirs(mugshots_dir)
            print(f"📁 Created directory: {mugshots_dir}/")
        
        # Strip the header if present
        if ',' in data_url:
            header, encoded = data_url.split(',', 1)
        else:
            header = ""
            encoded = data_url

        # Determine file extension
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "png" in header:
            ext = "png"
        else:
            ext = "jpg"  # default

        # Create filename with folder path
        filename = f"{filename_prefix}.{ext}"
        filepath = os.path.join(mugshots_dir, filename)
        
        # Save the image to disk
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(encoded))
        
        print(f"✅ Saved mugshot image: {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ Error converting image: {e}")
        return None

def get_api_credentials():
    """Get API credentials from environment variables"""
    return {
        'access_token': os.getenv('ACCESS_TOKEN', ''),
        'app_id': os.getenv('APP_ID', ''),
        'business_id': os.getenv('BUSINESS_ID', '')
    }

def generate_caption(data):
    """Generate consistent Instagram caption from extracted data"""
    try:
        name = data.get('Full Name', 'Unknown')
        charge = data.get('Charge 1', 'No charge listed')
        bail = data.get('Bail', 'No bail information')
        
        # Clean up the data
        name = name.strip()
        charge = charge.strip()
        bail = bail.strip()
        
        # Validate and clean bail information
        # If bail is missing, empty, or contains invalid content, show N/A
        invalid_bail_patterns = [
            'No bail information',
            'No Bail Information',
            'Next Court Appearance:',
            'Next Court Appearance',
            'None',
            'Unknown'
        ]
        
        # Check if bail should be N/A
        bail_upper = bail.upper()
        should_show_na = (
            not bail or 
            bail.strip() == '' or
            any(pattern in bail for pattern in invalid_bail_patterns) or
            'NEXT COURT APPEARANCE' in bail_upper
        )
        
        # Set bail display value
        if should_show_na:
            bail_display = 'N/A'
        else:
            bail_display = bail
        
        # Build charge line only when a real charge is present
        invalid_charge_values = ['No charge listed', 'Charge information not available', '']
        charge_line = ""
        if charge not in invalid_charge_values:
            label = "CHARGES" if Config.CHARGE_SEPARATOR in charge else "CHARGE"
            charge_line = f"{label}: {charge}\n"

        caption = f"""
{charge_line}NAME: {name}
BAIL: {bail_display}

Arrest Date: {data.get('Booking_Date') or get_current_date()}
Hennepin County, MN

{Config.DISCLAIMER}

#minneapolismugshots #HennepinCounty #Arrest #PublicRecord #Minnesota #Minneapolis"""
        
        return caption
        
    except Exception as e:
        print(f"❌ Error generating caption: {e}")
        return f"🚨 Minneapolis Arrest Alert - {data.get('Full Name', 'Unknown')}"

def post_to_instagram(image_url, caption, credentials, test_mode=False, video_url=None):
    """Post an image, or a Reel when video_url is given, using the Meta API"""
    try:
        access_token = credentials['access_token']
        business_id = credentials['business_id']
        
        if not access_token or not business_id:
            print("❌ Missing Meta API credentials")
            return False
        
        # Test mode - just simulate posting
        if test_mode:
            print(f"🧪 TEST MODE - Would post to Instagram:")
            print(f"   📸 {'Reel: ' + video_url if video_url else 'Image: ' + image_url}")
            print(f"   📝 Caption: {caption[:100]}...")
            print(f"   🎯 Business ID: {business_id}")
            print(f"✅ TEST MODE - Post simulation successful")
            return True
        
        # Step 1: Create media object
        print(f"📸 Creating Instagram media for: {image_url}")
        
        media_url = f"https://graph.facebook.com/v23.0/{business_id}/media"
        media_params = {'caption': caption, 'access_token': access_token}
        if video_url:
            media_params.update({'media_type': 'REELS', 'video_url': video_url, 'share_to_feed': 'true'})
        else:
            media_params['image_url'] = image_url
        
        media_response = requests.post(media_url, data=media_params)
        
        if media_response.status_code != 200:
            print(f"❌ Failed to create media: {media_response.status_code}")
            print(f"Response: {media_response.text}")
            return False
        
        media_data = media_response.json()
        media_id = media_data.get('id')
        
        if not media_id:
            print(f"❌ No media ID returned: {media_data}")
            return False
        
        print(f"✅ Media created with ID: {media_id}")

        # Instagram processes the image asynchronously; publishing before it
        # finishes fails with "Media ID is not available". Wait for FINISHED.
        # Videos take longer: up to 5 minutes, images up to 1.
        for attempt in range(60 if video_url else 12):
            status = requests.get(
                f"https://graph.facebook.com/v23.0/{media_id}",
                params={'fields': 'status_code', 'access_token': access_token},
            ).json().get('status_code')
            if status == 'FINISHED':
                break
            if status in ('ERROR', 'EXPIRED'):
                print(f"❌ Media processing failed: {status}")
                return False
            print(f"⏳ Media status: {status}, waiting...")
            time.sleep(5)
        
        # Step 2: Publish the media
        print(f"📤 Publishing media to Instagram...")
        
        publish_url = f"https://graph.facebook.com/v23.0/{business_id}/media_publish"
        publish_params = {
            'creation_id': media_id,
            'access_token': access_token
        }
        
        publish_response = requests.post(publish_url, data=publish_params)
        
        if publish_response.status_code != 200:
            print(f"❌ Failed to publish media: {publish_response.status_code}")
            print(f"Response: {publish_response.text}")
            return False
        
        publish_data = publish_response.json()
        post_id = publish_data.get('id')
        
        if post_id:
            print(f"🎉 Successfully posted to Instagram! Post ID: {post_id}")
            return True
        else:
            print(f"❌ No post ID returned: {publish_data}")
            return False
            
    except Exception as e:
        print(f"❌ Error posting to Instagram: {e}")
        return False

def parse_bail_amount(bail_string):
    """
    Parse bail string and return numeric value for sorting
    Returns 999999999 for 'NO BAIL' cases (highest priority)
    Returns 0 for unparseable amounts
    """
    try:
        if not bail_string or bail_string.strip() == '':
            return 0
        
        bail_upper = bail_string.upper().strip()
        
        # Handle special cases
        if 'NO BAIL' in bail_upper or 'HOLD WITHOUT BAIL' in bail_upper:
            return 999999999  # Highest priority
        
        if 'RELEASED' in bail_upper or 'NO BAIL INFORMATION' in bail_upper:
            return 0  # Lowest priority
        
        # Extract dollar amount using regex
        money_pattern = r'\$[\d,]+\.?\d*'
        matches = re.findall(money_pattern, bail_string)
        
        if matches:
            # Take the first dollar amount found
            amount_str = matches[0].replace('$', '').replace(',', '')
            return float(amount_str)
        
        return 0
        
    except Exception as e:
        print(f"⚠️  Error parsing bail amount '{bail_string}': {e}")
        return 0

def filter_top_bail_inmates(data_list, top_n=10):
    """
    Filter inmates for Instagram posting prioritization
    Takes all inmates with mugshots, prioritizes by charge status then bail amount
    Priority order: 1) Mugshot + Charge + Highest Bail, 2) Mugshot + Charge + Lower/No Bail, 3) Mugshot + No Charge
    
    Args:
        data_list: List of inmate dictionaries (already filtered for mugshot)
        top_n: Number of top inmates to return (default 10)
    
    Returns:
        List of top N inmates sorted by priority (charge first, then bail amount)
    """
    try:
        print(f"\n🔍 Prioritizing {top_n} inmates for Instagram posting (by charge status then bail amount)...")
        
        if not data_list:
            print("❌ No inmates to filter")
            return []
        
        # Add charge status and parsed bail amount to each inmate for sorting
        inmates_for_posting = []
        
        for inmate in data_list:
            bail_str = inmate.get('Bail', '')
            charge_str = inmate.get('Charge 1', '')
            bail_amount = parse_bail_amount(bail_str)
            
            # Determine charge status (valid charge = True, no charge = False)
            has_valid_charge = (
                charge_str and 
                charge_str.strip() and
                charge_str != 'No charge listed' and
                not charge_str.endswith(':') and
                len(charge_str) > 5
            )
            
            # All inmates in data_list already have mugshots
            inmates_for_posting.append({
                **inmate,
                '_bail_amount': bail_amount,
                '_has_charge': has_valid_charge
            })
            
            charge_status = "✅ Has charge" if has_valid_charge else "❌ No charge"
            bail_display = f"${bail_amount:,.2f}" if bail_amount > 0 else "No bail info"
            print(f"📊 {inmate.get('Full Name', 'Unknown')}: {charge_status} | {bail_str} → {bail_display}")
        
        print(f"\n📊 {len(inmates_for_posting)} inmates available for posting prioritization")
        
        # Sort by charge status first (True before False), then by bail amount (highest first)
        sorted_inmates = sorted(inmates_for_posting, key=lambda x: (not x['_has_charge'], -x['_bail_amount']))
        
        # Take top N and remove the temporary sorting fields
        top_inmates = []
        for i, inmate in enumerate(sorted_inmates[:top_n]):
            # Remove the temporary sorting fields
            filtered_inmate = {k: v for k, v in inmate.items() if k not in ['_bail_amount', '_has_charge']}
            top_inmates.append(filtered_inmate)
            
            bail_amount = inmate['_bail_amount']
            has_charge = inmate['_has_charge']
            
            if bail_amount == 999999999:
                bail_display = "NO BAIL"
            elif bail_amount > 0:
                bail_display = f"${bail_amount:,.2f}"
            else:
                bail_display = "No bail info"
            
            charge_status = "✅ Has charge" if has_charge else "❌ No charge"
            print(f"🏆 #{i+1}: {inmate.get('Full Name', 'Unknown')} - {charge_status} | {bail_display}")
        
        print(f"\n✅ Prioritized {len(top_inmates)} inmates for Instagram posting (by charge status then bail amount)")
        return top_inmates
        
    except Exception as e:
        print(f"❌ Error filtering inmates: {e}")
        return data_list  # Return original list on error

def save_to_posting_queue(data_list):
    """Save inmates to posting queue for staggered posting"""

    def filter_priority_inmates(d, n=10):
        """Rank by: has a charge, then distinctiveness (CLIP, rescaled 0..1 per batch)
        plus a severity bonus, then bail. If CLIP can't run, distinctiveness is 0."""
        def get_bail_amount(bail_str):
            match = re.search(r'\$[\d,]+\.?\d*', bail_str or '')
            return float(match.group()[1:].replace(',', '')) if match else 0

        def has_charge(inmate):
            return inmate.get('Charge 1', 'No charge listed') != 'No charge listed'

        def severity(inmate):
            return most_severe([inmate.get('Severity', ''), inmate.get('Charge 1', '')]) if has_charge(inmate) else ''

        raw = {}
        try:
            from mugshot_ranker import score_mugshots
            raw = score_mugshots([i['Mugshot_File'] for i in d if os.path.exists(i.get('Mugshot_File', ''))])
        except Exception as e:
            print(f"⚠️  Distinctiveness ranking unavailable, using severity + bail only: {e}")

        # Rescale to 0..1 within today's batch so the spread is comparable to the severity bonus
        lo, hi = min(raw.values(), default=0), max(raw.values(), default=0)
        distinct = {p: (v - lo) / (hi - lo) if hi > lo else 0 for p, v in raw.items()}

        def total(inmate):
            return distinct.get(inmate.get('Mugshot_File'), 0) + Config.SEVERITY_BONUS[severity(inmate)]

        ranked = sorted(d, key=lambda i: (not has_charge(i), -total(i), -get_bail_amount(i.get('Bail', ''))))
        for i, inmate in enumerate(ranked[:n], 1):
            print(f"🏆 #{i}: {inmate.get('Full Name')} | total {total(inmate):.2f} = "
                  f"distinct {distinct.get(inmate.get('Mugshot_File'), 0):.2f} + {severity(inmate) or 'no severity'}")
        return ranked[:n]

    print(f"💾 Creating posting queue with {len(data_list)} inmates...")
    
    # Never re-queue anyone the current queue already posted (same-day re-scrapes)
    try:
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            already_posted = {i['data'].get('Full Name') for i in json.load(f)['inmates'] if i.get('posted')}
    except Exception:
        already_posted = set()
    if already_posted:
        print(f"⏭️  Skipping {len(already_posted)} already posted: {', '.join(sorted(already_posted))}")
        data_list = [d for d in data_list if d.get('Full Name') not in already_posted]

    # Filter to top 10 highest priority inmates BEFORE creating queue
    filtered_inmates = filter_priority_inmates(data_list, n=10)
    booking_date = get_current_date()
    for d in filtered_inmates:
        d['Booking_Date'] = booking_date
    
    # Add timestamp and posting status to each inmate
    queue_data = {
        'created_at': get_current_datetime_iso(),
        'total_inmates': len(filtered_inmates),
        'posted_count': 0,
        'inmates': []
    }
    
    for i, data in enumerate(filtered_inmates):
        inmate = {
            'id': i + 1,
            'data': data,
            'posted': False,
            'posted_at': None
        }
        queue_data['inmates'].append(inmate)
    
    # Save to JSON file
    with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(queue_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Posting queue saved successfully")
    print(f"📊 Queue stats: {len(filtered_inmates)} inmates prioritized for posting")
    print(f"🎯 Prioritized from {len(data_list)} total inmates to top 10 by charge, distinctiveness + severity, then bail")

    return True

def get_next_inmates_to_post(batch_size=1):
    """Get next inmate to post from queue (single posting)"""
    try:
        # Load queue
        try:
            with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
        except FileNotFoundError:
            print("📭 No posting queue found")
            return []
        
        # Find unposted inmates
        unposted_inmates = [inmate for inmate in queue_data['inmates'] if not inmate['posted']]
        
        if not unposted_inmates:
            print("✅ All inmates have been posted!")
            return []
        
        # Get next single inmate
        next_inmate = unposted_inmates[:batch_size]
        
        print(f"📋 Found {len(next_inmate)} inmate ready to post")
        print(f"📊 Remaining in queue: {len(unposted_inmates)} total")
        
        # DEBUG: Check if mugshot files exist before processing
        for inmate in next_inmate:
            mugshot_path = inmate['data'].get('Mugshot_File', '')
            name = inmate['data'].get('Full Name', 'Unknown')
            print(f"🔍 DEBUG: Processing {name}")
            print(f"🔍 DEBUG: Expected mugshot path: {mugshot_path}")
            print(f"🔍 DEBUG: File exists: {os.path.exists(mugshot_path) if mugshot_path else False}")
            
            # Check current working directory and file listing
            print(f"🔍 DEBUG: Current working directory: {os.getcwd()}")
            if os.path.exists('mugshots'):
                mugshot_files = [f for f in os.listdir('mugshots') if f.endswith('.jpg')]
                print(f"🔍 DEBUG: Available mugshot files: {mugshot_files}")
            else:
                print(f"🔍 DEBUG: Mugshots directory does not exist!")
        
        return next_inmate
        
    except Exception as e:
        print(f"❌ Error reading posting queue: {e}")
        return []

def _delete_file_if_exists(path: str, label: str = ""):
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"🗑️  Deleted {label or 'file'}: {path}")
            return True
        else:
            print(f"⚠️  {label or 'File'} not found: {path}")
            return False
    except Exception as e:
        print(f"❌ Failed to delete {label or 'file'} {path}: {e}")
        return False

def delete_mugshot_files(inmate_ids):
    """Delete mugshot files for posted inmates to save disk space (both repo and docs copies)."""
    try:
        # Load queue to get mugshot file paths
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        
        deleted_count = 0
        failed_deletions = []
        
        for inmate in queue_data['inmates']:
            if inmate['id'] in inmate_ids:
                mugshot_file = inmate['data'].get('Mugshot_File', '')
                name = inmate['data'].get('Full Name', 'Unknown')
                
                if mugshot_file and mugshot_file != 'No Image':
                    # Ensure it's a local file path
                    if not mugshot_file.startswith('mugshots/'):
                        mugshot_file = f"mugshots/{mugshot_file}"
                    
                    # Delete from repo mugshots/
                    if _delete_file_if_exists(mugshot_file, label="mugshot"):
                        deleted_count += 1
                    else:
                        failed_deletions.append((mugshot_file, "not_found"))

                    # Delete corresponding docs/mugshots copy if present
                    docs_copy = os.path.join('docs', 'mugshots', os.path.basename(mugshot_file))
                    _ = _delete_file_if_exists(docs_copy, label="docs mugshot")
        
        print(f"🗑️  Cleanup Summary: {deleted_count} files deleted")
        if failed_deletions:
            print(f"⚠️  Failed deletions: {len(failed_deletions)}")
            for file_path, error in failed_deletions:
                print(f"   {file_path}: {error}")
        
        return deleted_count > 0
        
    except Exception as e:
        print(f"❌ Error during mugshot cleanup: {e}")
        return False

def mark_inmates_as_posted(inmate_ids):
    """Mark inmates as posted in the queue and delete their mugshot files"""
    try:
        # Load queue
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        
        # Mark as posted
        posted_count = 0
        for inmate in queue_data['inmates']:
            if inmate['id'] in inmate_ids:
                inmate['posted'] = True
                inmate['posted_at'] = get_current_datetime_iso()
                posted_count += 1
        
        # Update stats
        queue_data['posted_count'] = sum(1 for inmate in queue_data['inmates'] if inmate['posted'])
        
        # Save updated queue
        with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Marked {posted_count} inmates as posted")
        print(f"📊 Total posted: {queue_data['posted_count']}/{queue_data['total_inmates']}")
        
        # Delete mugshot files for posted inmates
        if posted_count > 0:
            print(f"🗑️  Starting mugshot cleanup for {posted_count} posted inmates...")
            delete_mugshot_files(inmate_ids)
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating posting queue: {e}")
        return False

def cleanup_unposted_mugshots():
    """Delete mugshot files for all inmates that remain unposted, and prune them from the queue."""
    try:
        print("🧹 Cleaning up UNPOSTED inmates' mugshots and pruning queue...")
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)

        unposted_ids = [i['id'] for i in queue_data['inmates'] if not i.get('posted')]
        posted_ids = [i['id'] for i in queue_data['inmates'] if i.get('posted')]

        # Delete files for all unposted inmates (both repo and docs copies)
        for inmate in queue_data['inmates']:
            if inmate['id'] in unposted_ids:
                mugshot_file = inmate['data'].get('Mugshot_File', '')
                if mugshot_file and mugshot_file != 'No Image':
                    if not mugshot_file.startswith('mugshots/'):
                        mugshot_file = f"mugshots/{mugshot_file}"
                    _delete_file_if_exists(mugshot_file, label="mugshot")
                    docs_copy = os.path.join('docs', 'mugshots', os.path.basename(mugshot_file))
                    _delete_file_if_exists(docs_copy, label="docs mugshot")

        # Prune unposted inmates from queue
        queue_data['inmates'] = [i for i in queue_data['inmates'] if i['id'] in posted_ids]
        queue_data['total_inmates'] = len(queue_data['inmates'])
        queue_data['posted_count'] = sum(1 for i in queue_data['inmates'] if i.get('posted'))

        with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, indent=2, ensure_ascii=False)

        print("✅ Unposted mugshots cleaned and queue pruned")
        return True
    except FileNotFoundError:
        print("📭 No posting queue found; nothing to clean")
        return True
    except Exception as e:
        print(f"❌ Error cleaning unposted mugshots: {e}")
        return False

def cleanup_all_mugshots():
    """Delete ALL mugshot files from repo and docs regardless of queue."""
    try:
        print("🧹 Cleaning up ALL mugshot files (repo and docs)...")
        deleted = 0
        for base in ['mugshots', os.path.join('docs', 'mugshots')]:
            if os.path.isdir(base):
                for fn in os.listdir(base):
                    if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                        path = os.path.join(base, fn)
                        if _delete_file_if_exists(path, label="mugshot"):
                            deleted += 1
        print(f"✅ All cleanup complete. Files deleted: {deleted}")
        return True
    except Exception as e:
        print(f"❌ Error cleaning all mugshots: {e}")
        return False

def purge_unqueued_mugshots():
    """Delete every mugshot not needed by an unposted queue entry.
    Skips entirely if the queue can't be read, so a broken scrape never wipes upcoming posts."""
    try:
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        keep = {os.path.basename(i['data'].get('Mugshot_File', ''))
                for i in queue_data['inmates'] if not i.get('posted')}
    except Exception as e:
        print(f"⚠️  Queue unreadable, skipping mugshot purge: {e}")
        return False

    deleted = 0
    if os.path.isdir(Config.MUGSHOTS_DIR):
        for fn in os.listdir(Config.MUGSHOTS_DIR):
            if fn.lower().endswith(('.jpg', '.jpeg', '.png')) and fn not in keep:
                os.remove(os.path.join(Config.MUGSHOTS_DIR, fn))
                deleted += 1
    print(f"🧹 Purged {deleted} mugshots not in the posting queue (kept {len(keep)})")
    return True

def post_next_inmates(batch_size=1, repo_name="minneapolismugshots", username="ryanjhermes", test_mode=False):
    """Post next inmate from queue (single posting)"""
    try:
        print(f"\n📱 Starting single Instagram posting...")
        
        # Get next inmate to post
        inmates_to_post = get_next_inmates_to_post(batch_size)
        
        if not inmates_to_post:
            print("📭 No inmates to post at this time")
            return True
        
        # Get API credentials
        credentials = get_api_credentials()
        
        if not credentials['access_token']:
            print("⚠️  No Meta API credentials found - skipping Instagram posting")
            return False
        
        successful_posts = []
        failed_posts = []
        
        for inmate in inmates_to_post:
            try:
                inmate_data = inmate['data']
                inmate_id = inmate['id']
                
                print(f"\n{'='*40}")
                print(f"📱 Posting inmate #{inmate_id}: {inmate_data.get('Full Name', 'Unknown')}")
                print(f"{'='*40}")
                
                # Convert local file path to GitHub Pages URL
                mugshot_file = inmate_data.get('Mugshot_File', '')
                if mugshot_file.startswith('mugshots/'):
                    filename = mugshot_file.replace('mugshots/', '')
                else:
                    filename = os.path.basename(mugshot_file)
                
                image_url = f"https://{username}.github.io/{repo_name}/mugshots/{filename}"
                print(f"🖼️  Image URL: {image_url}")
                
                # Generate caption
                caption = generate_caption(inmate_data)
                print(f"📝 Caption preview: {caption[:100]}...")
                
                # Post as a Reel when one was rendered, falling back to the still image
                success = False
                if inmate_data.get('Reel_File'):
                    reel_url = f"{Config.PAGES_URL}/{inmate_data['Reel_File']}"
                    success = post_to_instagram(image_url, caption, credentials, test_mode, video_url=reel_url)
                    if not success:
                        print("⚠️  Reel failed, falling back to image post")
                if not success:
                    success = post_to_instagram(image_url, caption, credentials, test_mode)
                
                if success:
                    successful_posts.append(inmate_id)
                    print(f"✅ Successfully posted {inmate_data.get('Full Name', 'Unknown')}")
                else:
                    failed_posts.append(inmate_id)
                    print(f"❌ Failed to post {inmate_data.get('Full Name', 'Unknown')}")
                
                # No need for delays between posts since we're only posting one at a time
                
            except Exception as e:
                print(f"❌ Error processing inmate #{inmate_id}: {e}")
                failed_posts.append(inmate_id)
                continue
        
        # Mark successful posts as completed
        if successful_posts:
            mark_inmates_as_posted(successful_posts)
        
        # Summary
        print(f"\n📊 SINGLE POSTING SUMMARY:")
        print(f"   ✅ Successful posts: {len(successful_posts)}")
        print(f"   ❌ Failed posts: {len(failed_posts)}")
        print(f"   📱 Total posted: {len(inmates_to_post)}")
        
        return len(successful_posts) > 0
        
    except Exception as e:
        print(f"❌ Error in single posting process: {e}")
        return False

def post_all_to_instagram(data_list, repo_name="minneapolismugshots", username="ryanjhermes", test_mode=False):
    """Post all scraped data to Instagram"""
    try:
        print(f"\n📱 Starting Instagram posting process...")
        
        # Get API credentials
        credentials = get_api_credentials()
        
        if not credentials['access_token']:
            print("⚠️  No Meta API credentials found - skipping Instagram posting")
            return False
        
        successful_posts = 0
        failed_posts = 0
        
        for i, data in enumerate(data_list, 1):
            try:
                print(f"\n{'='*50}")
                print(f"📱 Posting {i}/{len(data_list)}: {data.get('Full Name', 'Unknown')}")
                print(f"{'='*50}")
                
                # Convert local file path to GitHub Pages URL
                mugshot_file = data.get('Mugshot_File', '')
                if mugshot_file.startswith('mugshots/'):
                    filename = mugshot_file.replace('mugshots/', '')
                else:
                    filename = os.path.basename(mugshot_file)
                
                image_url = f"https://{username}.github.io/{repo_name}/mugshots/{filename}"
                print(f"🖼️  Image URL: {image_url}")
                
                # Generate caption
                caption = generate_caption(data)
                print(f"📝 Caption preview: {caption[:100]}...")
                
                # Post to Instagram
                success = post_to_instagram(image_url, caption, credentials, test_mode)
                
                if success:
                    successful_posts += 1
                    print(f"✅ Successfully posted {data.get('Full Name', 'Unknown')}")
                    
                    # Wait between posts to avoid rate limiting
                    if i < len(data_list):  # Don't wait after the last post
                        print("⏳ Waiting 30 seconds before next post...")
                        time.sleep(30)
                else:
                    failed_posts += 1
                    print(f"❌ Failed to post {data.get('Full Name', 'Unknown')}")
                
            except Exception as e:
                print(f"❌ Error processing {data.get('Full Name', 'Unknown')}: {e}")
                failed_posts += 1
                continue
        
        # Summary
        print(f"\n📊 INSTAGRAM POSTING SUMMARY:")
        print(f"   ✅ Successful posts: {successful_posts}")
        print(f"   ❌ Failed posts: {failed_posts}")
        print(f"   📱 Total processed: {len(data_list)}")
        
        return successful_posts > 0
        
    except Exception as e:
        print(f"❌ Error in Instagram posting process: {e}")
        return False

def get_current_date():
    """
    Get the current date in Central Time in MM/DD/YYYY format (as expected by this website)
    Always uses Central Time regardless of server timezone
    """
    from datetime import datetime
    import pytz
    
    try:
        # Get current time in Central Time zone
        central_tz = pytz.timezone('US/Central')
        central_time = datetime.now(central_tz)
        current_date = central_time.strftime("%m/%d/%Y")
        print(f"📅 Current date (Central Time): {current_date}")
        return current_date
    except ImportError:
        # Fallback if pytz not available - subtract 6 hours (Central is UTC-6 in summer, UTC-5 in winter)
        # This is a rough approximation for cases where pytz isn't installed
        from datetime import datetime, timedelta
        utc_time = datetime.utcnow()
        # Approximate Central Time (CST/CDT is UTC-6 in summer)
        central_time = utc_time - timedelta(hours=6)
        current_date = central_time.strftime("%m/%d/%Y")
        print(f"📅 Current date (Central Time approx): {current_date}")
        return current_date

def get_current_datetime_iso():
    """
    Get the current datetime in Central Time in ISO format for internal tracking
    Always uses Central Time regardless of server timezone
    """
    from datetime import datetime
    import pytz
    
    try:
        # Get current time in Central Time zone
        central_tz = pytz.timezone('US/Central')
        central_time = datetime.now(central_tz)
        return central_time.isoformat()
    except ImportError:
        # Fallback if pytz not available
        from datetime import datetime, timedelta
        utc_time = datetime.utcnow()
        # Approximate Central Time (CST/CDT is UTC-6 in summer)
        central_time = utc_time - timedelta(hours=6)
        return central_time.isoformat()

def get_date_range(days_back=7):
    """
    Get a date range from X days ago to today
    
    Args:
        days_back: Number of days to go back from today
    
    Returns:
        tuple: (start_date, end_date) in MM/DD/YYYY format
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    start_str = start_date.strftime("%m/%d/%Y")
    end_str = end_date.strftime("%m/%d/%Y")
    
    print(f"📅 Date range: {start_str} to {end_str} ({days_back} days)")
    return start_str, end_str

def input_date_field(driver, date_value, field_identifier="minDate"):
    """
    Input data into a date field
    
    Args:
        driver: Selenium WebDriver instance
        date_value: Date string in MM/DD/YYYY format
        field_identifier: How to identify the field (formcontrolname, id, etc.)
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    
    try:
        print(f"Looking for date field with identifier: {field_identifier}")
        
        # Try multiple ways to find the date input field
        date_input = None
        
        # Method 1: By formcontrolname attribute
        try:
            date_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, f'input[formcontrolname="{field_identifier}"]'))
            )
            print("✅ Found date field by formcontrolname")
        except:
            pass
        
        # Method 2: By type="date"
        if not date_input:
            try:
                date_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="date"]')
                if date_inputs:
                    # For minDate, take first field; for maxDate, take second field
                    if field_identifier == "minDate" and len(date_inputs) > 0:
                        date_input = date_inputs[0]
                        print("✅ Found first date field by type='date'")
                    elif field_identifier == "maxDate" and len(date_inputs) > 1:
                        date_input = date_inputs[1]
                        print("✅ Found second date field by type='date'")
                    else:
                        date_input = date_inputs[0]
                        print("✅ Found date field by type='date'")
            except:
                pass
        
        if date_input:
            print(f"📍 Field info - Tag: {date_input.tag_name}, Type: {date_input.get_attribute('type')}")
            print(f"📍 Field attributes - ID: {date_input.get_attribute('id')}, Name: {date_input.get_attribute('formcontrolname')}")
            
            # Scroll to element and focus
            driver.execute_script("arguments[0].scrollIntoView(true);", date_input)
            time.sleep(0.5)
            
            # Check initial value
            initial_value = date_input.get_attribute('value')
            print(f"📍 Initial field value: '{initial_value}'")
            
            # Convert MM/DD/YYYY to YYYY-MM-DD (HTML5 standard)
            try:
                month, day, year = date_value.split('/')
                html5_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                print(f"📍 Using HTML5 date format: {date_value} → {html5_date}")
            except:
                html5_date = date_value
                print(f"📍 Using original date format: {date_value}")
            
            # Method 1: Careful JavaScript approach
            try:
                print("🔄 Trying Method 1: Careful JavaScript")
                
                # First, ensure field is editable
                driver.execute_script("arguments[0].removeAttribute('readonly');", date_input)
                driver.execute_script("arguments[0].removeAttribute('disabled');", date_input)
                
                # Focus and clear thoroughly
                date_input.click()
                time.sleep(0.3)
                date_input.clear()
                time.sleep(0.3)
                
                # Clear via JavaScript too
                driver.execute_script("arguments[0].value = '';", date_input)
                time.sleep(0.3)
                
                # Set the value via JavaScript
                driver.execute_script(f"arguments[0].value = '{html5_date}';", date_input)
                
                # Trigger events to notify the form
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", date_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", date_input)
                driver.execute_script("arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));", date_input)
                
                time.sleep(1)
                
                # Check if value was set
                current_value = date_input.get_attribute('value')
                print(f"📍 Value after careful JavaScript: '{current_value}'")
                
                if current_value and current_value != initial_value:
                    print(f"✅ Method 1 SUCCESS: {current_value}")
                    return True
                else:
                    print("❌ Method 1 failed - no value change")
            except Exception as e:
                print(f"❌ Method 1 error: {e}")
            
            # Method 2: Character-by-character input with clear
            try:
                print("🔄 Trying Method 2: Character-by-character input")
                
                # Focus field
                date_input.click()
                time.sleep(0.3)
                
                # Clear completely using multiple methods
                date_input.clear()
                time.sleep(0.2)
                date_input.send_keys(Keys.CONTROL + "a")  # Select all
                time.sleep(0.2)
                date_input.send_keys(Keys.DELETE)  # Delete
                time.sleep(0.2)
                
                # Input HTML5 format slowly
                for char in html5_date:
                    date_input.send_keys(char)
                    time.sleep(0.1)  # Small delay between characters
                
                # Press Tab to complete the input
                date_input.send_keys(Keys.TAB)
                time.sleep(1)
                
                # Check if value was set
                current_value = date_input.get_attribute('value')
                print(f"📍 Value after character input: '{current_value}'")
                
                if current_value and current_value != initial_value:
                    print(f"✅ Method 2 SUCCESS: {current_value}")
                    return True
                else:
                    print("❌ Method 2 failed - no value change")
            except Exception as e:
                print(f"❌ Method 2 error: {e}")
            
            # Method 3: Try to find and use date picker if available
            try:
                print("🔄 Trying Method 3: Looking for date picker")
                
                # Look for calendar/date picker button near the field
                picker_selectors = [
                    f'button[aria-label*="calendar"]',
                    f'[class*="calendar"]',
                    f'[class*="date-picker"]',
                    f'.mat-datepicker-toggle'
                ]
                
                for selector in picker_selectors:
                    try:
                        picker_btn = driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"📍 Found potential date picker: {selector}")
                        picker_btn.click()
                        time.sleep(1)
                        print("✅ Clicked date picker - manual interaction needed")
                        return True
                    except:
                        continue
                        
                print("❌ No date picker found")
            except Exception as e:
                print(f"❌ Method 3 error: {e}")
            
            # Final check
            final_value = date_input.get_attribute('value')
            print(f"📍 Final field value: '{final_value}'")
            
            if final_value and final_value != initial_value:
                print(f"✅ Some method worked! Final value: {final_value}")
                return True
            else:
                print("❌ All methods failed - field remains unchanged")
                return False
            
        else:
            print("❌ Could not find the date input field")
            return False
            
    except Exception as e:
        print(f"❌ Error inputting date: {e}")
        return False

def select_dropdown_option(driver, option_text="100", dropdown_type="results_per_page"):
    """
    Select an option from a dropdown
    
    Args:
        driver: Selenium WebDriver instance
        option_text: Text of the option to select (e.g., "100")
        dropdown_type: Type of dropdown to identify
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
    
    try:
        print(f"🔽 Looking for dropdown to select option: {option_text}")
        
        dropdown = None
        
        # Method 1: Find select element with options containing our target
        try:
            # Look for select elements
            selects = driver.find_elements(By.CSS_SELECTOR, 'select')
            for select_elem in selects:
                options = select_elem.find_elements(By.TAG_NAME, 'option')
                for option in options:
                    if option_text in option.text:
                        dropdown = select_elem
                        print(f"✅ Found dropdown with {option_text} option")
                        break
                if dropdown:
                    break
        except Exception as e:
            print(f"Method 1 error: {e}")
        
        # Method 2: Look for specific pagination/results dropdown
        if not dropdown:
            try:
                # Look for dropdowns with pagination-related options
                selects = driver.find_elements(By.CSS_SELECTOR, 'select[class*="ng-"], cds-select select, select')
                for select_elem in selects:
                    select_html = select_elem.get_attribute('outerHTML')
                    if any(num in select_html for num in ['10', '25', '50', '100']):
                        dropdown = select_elem
                        print("✅ Found results per page dropdown")
                        break
            except Exception as e:
                print(f"Method 2 error: {e}")
        
        if dropdown:
            print(f"📍 Dropdown info - Tag: {dropdown.tag_name}, ID: {dropdown.get_attribute('id')}")
            
            # Scroll to dropdown and focus
            driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
            time.sleep(0.5)
            
            # Method 1: Use Selenium Select class
            try:
                print("🔄 Trying Method 1: Selenium Select")
                select = Select(dropdown)
                
                # Try different ways to select the option
                # First try by visible text
                try:
                    select.select_by_visible_text(option_text)
                    print(f"✅ Selected by visible text: {option_text}")
                    return True
                except:
                    pass
                
                # Try by value containing the text
                try:
                    for option in select.options:
                        if option_text in option.text or option_text in option.get_attribute('value'):
                            select.select_by_value(option.get_attribute('value'))
                            print(f"✅ Selected by value: {option.get_attribute('value')}")
                            return True
                except:
                    pass
                    
            except Exception as e:
                print(f"Method 1 error: {e}")
            
            # Method 2: Click the dropdown and then the option
            try:
                print("🔄 Trying Method 2: Click dropdown then option")
                
                # Click to open dropdown
                dropdown.click()
                time.sleep(1)
                
                # Find and click the specific option
                options = dropdown.find_elements(By.TAG_NAME, 'option')
                for option in options:
                    if option_text in option.text:
                        option.click()
                        print(f"✅ Clicked option: {option.text}")
                        time.sleep(0.5)
                        return True
                
            except Exception as e:
                print(f"Method 2 error: {e}")
            
            # Method 3: JavaScript approach
            try:
                print("🔄 Trying Method 3: JavaScript selection")
                
                # Find the option value for our target text
                options = dropdown.find_elements(By.TAG_NAME, 'option')
                target_value = None
                for option in options:
                    if option_text in option.text:
                        target_value = option.get_attribute('value')
                        break
                
                if target_value:
                    # Set value via JavaScript
                    driver.execute_script(f"arguments[0].value = '{target_value}';", dropdown)
                    
                    # Trigger change event
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", dropdown)
                    
                    print(f"✅ Set dropdown value via JavaScript: {target_value}")
                    return True
                    
            except Exception as e:
                print(f"Method 3 error: {e}")
            
            print("❌ All dropdown selection methods failed")
            return False
            
        else:
            print("❌ Could not find dropdown element")
            return False
            
    except Exception as e:
        print(f"❌ Error selecting dropdown option: {e}")
        return False

def extract_case_details(driver):
    """
    Extract and print all case details from the modal/popup
    """
    try:
        print("\n📋 Extracting case details from modal...")
        
        # Wait for modal to fully load
        time.sleep(2)
        
        case_data = {}
        all_text_data = []
        
        # Method 1: Extract from stacking-row elements specifically
        try:
            stacking_rows = driver.find_elements(By.CSS_SELECTOR, '[class*="stacking-row"], .hcso-stacking-row')
            print(f"📍 Found {len(stacking_rows)} stacking-row elements")
            
            for i, row in enumerate(stacking_rows):
                try:
                    row_text = row.text.strip()
                    if row_text:
                        all_text_data.append(f"Row {i+1}: {row_text}")
                        print(f"📄 Row {i+1}: {row_text}")
                except:
                    pass
                    
        except Exception as e:
            print(f"Method 1 error: {e}")
        
        # Method 2: Extract from modal content more broadly
        try:
            # Look for the modal/dialog container
            modal_selectors = [
                '[role="dialog"]',
                '.modal',
                '[class*="modal"]',
                '[class*="dialog"]',
                '[class*="case-details"]',
                '[class*="details"]'
            ]
            
            modal_content = None
            for selector in modal_selectors:
                try:
                    modal_content = driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"✅ Found modal with selector: {selector}")
                    break
                except:
                    continue
            
            if modal_content:
                # Extract structured data
                print(f"\n📋 CASE DETAILS EXTRACTION:")
                print("=" * 50)
                
                # Try to find specific fields
                field_patterns = [
                    ('Case Type:', 'case-type'),
                    ('MNCIS Case#:', 'case-number'),
                    ('Charged By:', 'charged-by'),
                    ('Clear Reason:', 'clear-reason'),
                    ('Hold Without Bail:', 'hold-without-bail'),
                    ('Bail Options:', 'bail-options'),
                    ('Next Court Appearance:', 'court-appearance'),
                    ('Description:', 'charge-description'),
                    ('Severity of Charge:', 'charge-severity'),
                    ('Statute:', 'statute'),
                    ('Charge Status:', 'charge-status')
                ]
                
                modal_text = modal_content.text
                lines = [line.strip() for line in modal_text.split('\n') if line.strip()]
                
                print("📝 ALL MODAL TEXT:")
                for i, line in enumerate(lines):
                    print(f"   {i+1:2d}. {line}")
                
                # Try to extract key-value pairs
                print(f"\n🔍 PARSED FIELDS:")
                current_section = ""
                
                for line in lines:
                    if any(pattern[0] in line for pattern in field_patterns):
                        # This looks like a field label
                        if ':' in line:
                            key, value = line.split(':', 1)
                            case_data[key.strip()] = value.strip()
                            print(f"   {key.strip()}: {value.strip()}")
                    elif line.startswith('Charge '):
                        current_section = line
                        print(f"\n📌 {line}")
                    elif current_section and line:
                        print(f"   └─ {line}")
                
            else:
                print("❌ Could not find modal container")
                
        except Exception as e:
            print(f"Method 2 error: {e}")
        
        # Method 3: Try to get all visible text elements in the page
        try:
            print(f"\n🔍 DETAILED ELEMENT EXTRACTION:")
            
            # Look for specific case detail elements
            detail_selectors = [
                '[class*="case"]',
                '[class*="charge"]',
                '[class*="detail"]',
                '[class*="field"]',
                'dt', 'dd',  # Definition terms and descriptions
                '.label', '.value',
                '[class*="info"]'
            ]
            
            for selector in detail_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(f"\n📍 Elements with selector '{selector}':")
                        for i, elem in enumerate(elements[:10]):  # Limit to first 10
                            text = elem.text.strip()
                            if text and len(text) < 200:  # Skip very long text
                                print(f"   {i+1}. {text}")
                except:
                    continue
                    
        except Exception as e:
            print(f"Method 3 error: {e}")
        
        return case_data
        
    except Exception as e:
        print(f"❌ Error extracting case details: {e}")
        return {}

def click_first_booking_id(driver):
    """
    Click on the first booking ID in the search results and extract details
    """
    try:
        print("\n🔍 Looking for booking IDs in search results...")
        
        # Wait for results to load
        time.sleep(2)
        
        booking_link = None
        
        # Method 1: Look for clickable booking numbers (typically links or buttons)
        try:
            # Look for elements that look like booking numbers (usually numeric, often starting with year)
            booking_selectors = [
                'a[href*="booking"]',  # Links with "booking" in href
                'button[class*="booking"]',  # Buttons with booking class
                'td a',  # Links in table cells
                '[class*="booking-number"] a',  # Booking number links
                'a[href*="detail"]',  # Detail page links
                '.booking-id a',  # Booking ID links
            ]
            
            for selector in booking_selectors:
                links = driver.find_elements(By.CSS_SELECTOR, selector)
                if links:
                    booking_link = links[0]  # Take the first one
                    print(f"✅ Found booking link with selector: {selector}")
                    break
                    
        except Exception as e:
            print(f"Method 1 error: {e}")
        
        # Method 2: Look for booking numbers by text pattern (numbers that look like booking IDs)
        if not booking_link:
            try:
                # Look for elements containing booking-number-like text (year + digits)
                all_links = driver.find_elements(By.CSS_SELECTOR, 'a, button[onclick], [role="button"]')
                
                for link in all_links:
                    text = link.text.strip()
                    # Look for patterns like 2025014936 (year + digits)
                    if text and len(text) >= 8 and text.startswith('202') and text.isdigit():
                        booking_link = link
                        print(f"✅ Found booking number by pattern: {text}")
                        break
                        
            except Exception as e:
                print(f"Method 2 error: {e}")
        
        # Method 3: Look in table rows for clickable elements
        if not booking_link:
            try:
                # Look for table rows and find clickable elements in first column
                rows = driver.find_elements(By.CSS_SELECTOR, 'tr, .row, [class*="row"]')
                
                for row in rows:
                    clickable_elements = row.find_elements(By.CSS_SELECTOR, 'a, button, [onclick], [role="button"]')
                    for element in clickable_elements:
                        text = element.text.strip()
                        if text and text.isdigit() and len(text) >= 8:
                            booking_link = element
                            print(f"✅ Found booking link in table row: {text}")
                            break
                    if booking_link:
                        break
                        
            except Exception as e:
                print(f"Method 3 error: {e}")
        
        if booking_link:
            booking_text = booking_link.text.strip()
            booking_tag = booking_link.tag_name
            booking_href = booking_link.get_attribute('href') or 'N/A'
            
            print(f"📍 Found booking link:")
            print(f"   Text: '{booking_text}'")
            print(f"   Tag: {booking_tag}")
            print(f"   Href: {booking_href}")
            print(f"   Classes: {booking_link.get_attribute('class')}")
            
            # Scroll to element
            driver.execute_script("arguments[0].scrollIntoView(true);", booking_link)
            time.sleep(1)
            
            # Highlight the element briefly (for visual confirmation)
            try:
                driver.execute_script("arguments[0].style.border='3px solid red';", booking_link)
                time.sleep(1)
                driver.execute_script("arguments[0].style.border='';", booking_link)
            except:
                pass
            
            print(f"🖱️  Clicking on booking ID: {booking_text}")
            booking_link.click()
            
            # Wait for page/modal to load
            time.sleep(3)
            
            # Report what happened
            new_url = driver.current_url
            new_title = driver.title
            
            print(f"✅ Successfully clicked booking ID!")
            print(f"📍 New URL: {new_url}")
            print(f"📍 New Page Title: {new_title}")
            
            # Extract case details from the modal/page
            case_details = extract_case_details(driver)
            
            return True
            
        else:
            print("❌ Could not find any booking IDs to click")
            
            # Debug: Print some page content to see what's available
            try:
                page_text = driver.find_element(By.TAG_NAME, 'body').text[:500]
                print(f"📍 Page content preview: {page_text}...")
            except:
                pass
                
            return False
            
    except Exception as e:
        print(f"❌ Error clicking booking ID: {e}")
        return False

def extract_key_details(driver):
    """
    Extract only the key details we need: Full Name, Charge 1, Bail, and Mugshot
    Uses the new FieldExtractor class for better organization and debugging
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    
    try:
        print("\n📋 Extracting key details using FieldExtractor...")
        
        # Use the new FieldExtractor class
        extractor = FieldExtractor(driver)
        extracted_data = extractor.extract_all_fields()
        
        return extracted_data
        
    except Exception as e:
        print(f"❌ Error in extract_key_details: {e}")
        return {
            'Full Name': 'Unknown',
            'Charge 1': 'No charge listed',
            'Bail': 'No bail information',
            'Mugshot_File': 'No Image'
        }

def close_modal(driver):
    """
    Close the current modal/dialog with better overlay handling
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    
    try:
        print("\n❌ Closing modal...")
        
        # Try multiple escape methods to ensure modal is closed
        for i in range(3):  # Try up to 3 times
            try:
                # Method 1: Press Escape key multiple times
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.5)
                
                # Method 2: Click outside the modal if it exists
                try:
                    overlay = driver.find_element(By.CSS_SELECTOR, '[class*="overlay"], [class*="backdrop"], .modal-backdrop')
                    if overlay:
                        overlay.click()
                        time.sleep(0.5)
                except:
                    pass
                
                # Method 3: Look for close buttons
                close_selectors = [
                    'button:contains("CLOSE")',
                    'button:contains("Close")', 
                    '[aria-label="Close"]',
                    '.close',
                    '.modal-close',
                    '[class*="close"]'
                ]
                
                for selector in close_selectors:
                    try:
                        close_button = driver.find_element(By.CSS_SELECTOR, selector)
                        if close_button.is_displayed():
                            close_button.click()
                            print(f"✅ Clicked close button: {selector}")
                            time.sleep(0.5)
                            break
                    except:
                        continue
                
            except:
                continue
        
        # Wait a moment for any animations to finish
        time.sleep(1)
        
        # Check if modal is still present
        try:
            modal = driver.find_element(By.CSS_SELECTOR, '[role="dialog"], .modal, [class*="modal"]')
            if modal.is_displayed():
                print("⚠️  Modal still visible, trying JavaScript removal")
                driver.execute_script("arguments[0].style.display = 'none';", modal)
                time.sleep(0.5)
        except:
            pass  # Modal is gone, which is good
        
        print("✅ Modal closing attempts completed")
        return True
                
    except Exception as e:
        print(f"❌ Error closing modal: {e}")
        return False

def save_to_csv(data_list, filename=Config.CSV_FILENAME):
    """
    Save the extracted data to a CSV file (overwrites existing file)
    """
    try:
        print(f"\n💾 Saving data to {filename}...")
        
        if not data_list:
            print("❌ No data to save")
            return False
        
        # Define CSV headers including mugshot filename
        headers = ['Full Name', 'Charge 1', 'Severity', 'Bail', 'Mugshot_File']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers, extrasaction='ignore')
            
            # Write header
            writer.writeheader()
            
            # Write data rows
            for data in data_list:
                writer.writerow(data)
        
        print(f"✅ Successfully saved {len(data_list)} records to {filename}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")
        return False

def get_all_booking_ids(driver, limit=100):
    """
    Get all booking IDs from the search results (limited for testing)
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    
    try:
        print(f"\n🔍 Finding all booking IDs (limit: {limit})...")
        
        booking_ids = []
        
        # Look for elements containing booking-number-like text
        all_clickable = driver.find_elements(By.CSS_SELECTOR, 'a, button[onclick], [role="button"], cds-button')
        
        for element in all_clickable:
            try:
                text = element.text.strip()
                # Look for patterns like booking IDs (typically 8-12 digit numbers)
                # Flexible pattern that works for any year/format
                if (text and 
                    text.isdigit() and 
                    len(text) >= 8 and 
                    len(text) <= 12 and
                    # Avoid very small numbers that are likely not booking IDs
                    int(text) > 10000000):  # Must be at least 8 digits with meaningful value
                    booking_ids.append({
                        'element': element,
                        'id': text
                    })
                    print(f"📋 Found booking ID: {text}")
                    
                    # Stop when we reach the limit
                    if len(booking_ids) >= limit:
                        break
            except:
                continue
        
        print(f"✅ Found {len(booking_ids)} booking IDs")
        return booking_ids
        
    except Exception as e:
        print(f"❌ Error getting booking IDs: {e}")
        return []

def process_multiple_bookings(driver, limit=3):
    """
    Process multiple booking IDs and extract data from each using BookingProcessor
    """
    try:
        print(f"\n🔄 Processing multiple bookings using BookingProcessor (limit: {limit})...")
        
        # Use the new BookingProcessor class
        processor = BookingProcessor(driver)
        all_extracted_data = processor.process_multiple_bookings(limit)
        
        return all_extracted_data
        
    except Exception as e:
        print(f"❌ Error processing multiple bookings: {e}")
        return []

def fill_form_with_current_date(driver, inmate_limit=Config.TEST_INMATE_LIMIT):
    """
    Fill the form, process multiple booking IDs, and save to CSV with top 10 highest bail filter
    """
    print("\n🗓️  Using current date for form input...")
    current_date = get_current_date()
    
    # Fill the "from" date (minDate)
    print("\n📅 Filling 'From' date field...")
    success_min = input_date_field(driver, current_date, "minDate")
    
    # Fill the "to" date (maxDate) - typically the same date for single day search
    print("\n📅 Filling 'To' date field...")
    success_max = input_date_field(driver, current_date, "maxDate")
    
    # Select 100 results per page
    print("\n🔽 Setting results per page to 100...")
    success_dropdown = select_dropdown_option(driver, "100", "results_per_page")
    
    if success_min or success_max:
        print(f"\n✅ Successfully filled form with today's date: {current_date}")
        if success_min and success_max:
            print("✅ Both 'from' and 'to' fields filled")
        elif success_min:
            print("⚠️  Only 'from' field filled")
        elif success_max:
            print("⚠️  Only 'to' field filled")
    else:
        print(f"\n❌ Failed to fill any date fields with: {current_date}")
    
    if success_dropdown:
        print("✅ Successfully set results per page to 100")
    else:
        print("⚠️  Could not set results per page to 100")
    
    # Wait a moment for any search to complete automatically
    print("\n⏳ Waiting for search results to load...")
    time.sleep(3)
    
    # Process more booking IDs to get better selection for filtering
    # inmate_limit is passed to the function as a parameter
    print(f"\n🚀 Starting batch processing of booking IDs (limit: inmate_limit)...")
    extracted_data_list = process_multiple_bookings(driver, limit=inmate_limit)
    
    # Save to CSV if we got data
    if extracted_data_list:
        # Use fixed filename (overwrites previous data)
        filename = Config.CSV_FILENAME
        
        success_save = save_to_csv(extracted_data_list, filename)
        
        if success_save:
            print(f"\n🎉 SUCCESS! Quality inmates (with mugshots + charges) saved to {filename}")
            print(f"\n📊 SUMMARY - READY FOR POSTING:")
            for i, data in enumerate(extracted_data_list, 1):
                mugshot_info = data.get('Mugshot_File', 'N/A')
                print(f"   {i}. {data.get('Full Name', 'N/A')} - {data.get('Charge 1', 'N/A')} - {data.get('Bail', 'N/A')} - Image: {mugshot_info}")
            
            # Save to posting queue (this will now filter to top 10 highest priority)
            print(f"\n📋 Saving quality inmates to posting queue...")
            queue_success = save_to_posting_queue(extracted_data_list)
            
            if queue_success:
                print(f"\n🚀 COMPLETE SUCCESS! Data scraped, filtered to TOP 10 HIGHEST PRIORITY, and queued for posting!")
                print(f"📅 Top 10 inmates will be posted throughout the day (up to 8 posts, every 3 hours)")
                print(f"🎲 Random delays added to avoid Instagram automation detection")
            else:
                print(f"\n⚠️  Data scraped and saved, but failed to create posting queue")
        else:
            print(f"\n⚠️  Data extracted but failed to save to CSV")
    else:
        print(f"\n❌ No data extracted from booking IDs")
    
    return success_min or success_max

def fill_form_with_date_range(driver, days_back=7):
    """
    Fill the form with a date range (X days ago to today)
    
    Args:
        driver: Selenium WebDriver instance
        days_back: Number of days to go back from today
    """
    print(f"\n📊 Using date range ({days_back} days back to today)...")
    start_date, end_date = get_date_range(days_back)
    
    # Input start date (minDate)
    success_min = input_date_field(driver, start_date, "minDate")
    time.sleep(1)
    
    # Input end date (maxDate) if there's a maxDate field
    success_max = input_date_field(driver, end_date, "maxDate")
    time.sleep(1)
    
    return success_min or success_max

def fill_search_form(driver, min_date=None, max_date=None):
    """
    Fill out the search form with date ranges
    
    Args:
        driver: Selenium WebDriver instance
        min_date: Minimum date in MM/DD/YYYY format (defaults to 7 days ago)
        max_date: Maximum date in MM/DD/YYYY format (defaults to today)
    """
    if not min_date:
        min_date = (datetime.now() - timedelta(days=7)).strftime("%m/%d/%Y")
    
    if not max_date:
        max_date = datetime.now().strftime("%m/%d/%Y")
    
    print(f"Filling search form with date range: {min_date} to {max_date}")
    
    # Input minimum date
    success_min = input_date_field(driver, min_date, "minDate")
    time.sleep(1)
    
    # Input maximum date (if there's a maxDate field)
    success_max = input_date_field(driver, max_date, "maxDate")
    time.sleep(1)
    
    # Try to find and click a search button
    try:
        # Look for common search button selectors
        search_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:contains("Search")',
            '.search-button',
            '#search-btn'
        ]
        
        search_button = None
        for selector in search_selectors:
            try:
                search_button = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
        
        if search_button:
            search_button.click()
            print("✅ Clicked search button")
        else:
            print("⚠️  Could not find search button")
            
    except Exception as e:
        print(f"⚠️  Error clicking search button: {e}")
    
    return success_min or success_max

def open_hennepin_jail_roster(inmate_limit=Config.DEFAULT_INMATE_LIMIT):
    """
    Opens the Hennepin County jail roster website using Selenium
    
    Args:
        inmate_limit: Maximum number of inmates to process (default from Config)
    """
    # Import selenium only when needed for scraping
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.support.ui import Select
    
    # Set up ChromeDriver service
    service = Service(ChromeDriverManager().install())
    
    # Configure Chrome options
    options = webdriver.ChromeOptions()
    
    # Check if running in CI environment (GitHub Actions)
    is_ci = os.getenv('CI') or os.getenv('GITHUB_ACTIONS')
    
    if is_ci:
        print("🤖 Running in CI environment - using headless mode")
        options.add_argument('--headless=new')  # Use new headless mode
        # Headless defaults to 800x600, which renders the booking modal in a narrow
        # layout where charges were never found. Match a desktop window instead.
        options.add_argument('--window-size=1920,1080')
    
    # Essential options for stability
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Create the driver
    driver = webdriver.Chrome(service=service, options=options)
    
    # Execute script to remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    try:
        print("Opening Hennepin County Jail Roster...")
        # Navigate to the jail roster website
        driver.get(Config.JAIL_ROSTER_URL)
        
        # Wait a moment for the page to load
        time.sleep(3)
        
        # Print current page title and URL
        print(f"Page Title: {driver.title}")
        print(f"Current URL: {driver.current_url}")
        
        # Check if the page loaded successfully or shows an error
        try:
            # Wait longer for dynamic content to load
            print("⏳ Waiting for page content to fully load...")
            time.sleep(5)  # Give more time for JavaScript to execute
            
            # Look for common error indicators
            page_source_lower = driver.page_source.lower()
            if "server unavailable" in page_source_lower and "disconnected" in page_source_lower:
                print("⚠️  Website appears to be unavailable or down")
                is_available = False
            else:
                print("✅ Website loaded successfully")
                is_available = True
                
            # Always try to fill the form, regardless of initial detection
            print("\n🗓️  Attempting to fill form with current date...")
            fill_form_with_current_date(driver, inmate_limit)
                
            # Try to find and print some basic page info
            try:
                # Wait for body element to load
                body = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                print(f"Page content length: {len(body.text)} characters")
                
                # Look for specific jail roster elements to confirm it's working
                form_elements = driver.find_elements(By.CSS_SELECTOR, 'input[type="date"], form, .search')
                if form_elements:
                    print(f"✅ Found {len(form_elements)} form elements - site appears functional")
                else:
                    print("⚠️  No form elements found")
                
            except Exception as e:
                print(f"Could not analyze page content: {e}")
                
        except Exception as e:
            print(f"Error analyzing page: {e}")
        
        # Processing complete - closing automatically
        print("\n✅ Processing complete! Closing browser...")
        time.sleep(2)  # Brief pause to see final status
        
    except Exception as e:
        print(f"Error opening website: {e}")
        
    finally:
        # Close the driver
        driver.quit()
        print("Browser closed.")

def test_instagram_posting():
    """Test Instagram posting with existing CSV data"""
    try:
        print("🧪 Testing Instagram posting with existing data...")
        
        # Read existing CSV data
        import csv
        data_list = []
        
        try:
            with open(Config.CSV_FILENAME, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    data_list.append(row)
            
            print(f"📊 Found {len(data_list)} records in CSV")
            
            if data_list:
                # Test posting (simulation mode)
                post_all_to_instagram(data_list, test_mode=True)
            else:
                print("❌ No data found in CSV file")
                
        except FileNotFoundError:
            print(f"❌ {Config.CSV_FILENAME} not found. Run scraping first.")
        except Exception as e:
            print(f"❌ Error reading CSV: {e}")
            
    except Exception as e:
        print(f"❌ Error in test: {e}")

def cleanup_existing_posted_mugshots():
    """Clean up mugshot files for inmates that were already posted but files weren't deleted"""
    try:
        print("🗑️  Cleaning up existing posted inmates' mugshots...")
        
        # Load queue
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        
        posted_inmates = [inmate for inmate in queue_data['inmates'] if inmate.get('posted', False)]
        
        if not posted_inmates:
            print("✅ No posted inmates found to clean up")
            return True
        
        inmate_ids = [inmate['id'] for inmate in posted_inmates]
        deleted_count = delete_mugshot_files(inmate_ids)
        
        if deleted_count:
            print(f"✅ Cleaned up {len(posted_inmates)} posted inmates' mugshots")
        else:
            print("⚠️  No mugshot files found to delete")
        
        return True
        
    except Exception as e:
        print(f"❌ Error cleaning up existing posted mugshots: {e}")
        return False

def check_posting_queue():
    """Check status of posting queue"""
    try:
        print("📋 Checking posting queue status...")
        
        try:
            with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            total = queue_data.get('total_inmates', 0)
            posted = queue_data.get('posted_count', 0)
            pending = total - posted
            
            print(f"📊 QUEUE STATUS:")
            print(f"   Total inmates: {total}")
            print(f"   Posted: {posted}")
            print(f"   Pending: {pending}")
            print(f"   Created: {queue_data.get('created_at', 'Unknown')}")
            
            if pending > 0:
                print(f"\n📋 Next inmate to post:")
                unposted = [inmate for inmate in queue_data['inmates'] if not inmate['posted']]
                for i, inmate in enumerate(unposted[:1], 1):
                    name = inmate['data'].get('Full Name', 'Unknown')
                    print(f"   {i}. {name}")
            else:
                print("✅ All inmates have been posted!")
            
            # Check for cleanup opportunity
            if posted > 0:
                print(f"\n🗑️  Cleanup Status:")
                posted_inmates = [inmate for inmate in queue_data['inmates'] if inmate.get('posted', False)]
                mugshot_files_exist = 0
                
                for inmate in posted_inmates:
                    mugshot_file = inmate['data'].get('Mugshot_File', '')
                    if mugshot_file and mugshot_file != 'No Image':
                        if not mugshot_file.startswith('mugshots/'):
                            mugshot_file = f"mugshots/{mugshot_file}"
                        if os.path.exists(mugshot_file):
                            mugshot_files_exist += 1
                
                if mugshot_files_exist > 0:
                    print(f"   ⚠️  {mugshot_files_exist} posted inmates still have mugshot files")
                    print(f"   💡 Run cleanup_existing_posted_mugshots() to delete them")
                else:
                    print(f"   ✅ All posted inmates' mugshots have been cleaned up")
                
        except FileNotFoundError:
            print("📭 No posting queue found")
            print("💡 Run 'python data.py' to create a queue")
            
    except Exception as e:
        print(f"❌ Error checking queue: {e}")

def posting_mode():
    """Decide what this posting run should do: 'post', 'recap' or '' (nothing), plus a reason.
    Scheduled runs act only in their Central-time slot; manual runs post whatever is pending."""
    try:
        with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
            q = json.load(f)
    except Exception as e:
        return '', f'no_queue ({e})'

    central = pytz.timezone('US/Central')
    now = datetime.now(central)
    posted_times = [datetime.fromisoformat(i['posted_at']).astimezone(central)
                    for i in q['inmates'] if i.get('posted') and i.get('posted_at')]
    pending = sum(1 for i in q['inmates'] if not i.get('posted'))
    recap_ready = bool(q.get('recap_file')) and not q.get('recap_posted_at')

    if os.getenv('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        if pending:
            return 'post', 'manual'
        return ('recap', 'manual') if recap_ready else ('', 'manual_nothing_pending')
    if now.hour == Config.RECAP_HOUR:
        return ('recap', 'recap_hour') if recap_ready else ('', 'recap_unavailable_or_posted')
    if now.hour not in Config.POSTING_HOURS:
        return '', f'outside_slots_{now.hour}'
    if any(t.date() == now.date() and t.hour == now.hour for t in posted_times):
        return '', f'already_posted_hour_{now.hour}'
    return ('post', f'slot_{now.hour}') if pending else ('', 'queue_empty')

def build_reels():
    """Render a Reel for each unposted queued inmate plus a Top 5 recap. Any failure leaves
    that entry without a reel, so posting falls back to the still image."""
    import reels
    with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
        q = json.load(f)
    os.makedirs(Config.REELS_DIR, exist_ok=True)

    for inmate in q['inmates']:
        d = inmate['data']
        d.pop('Reel_File', None)
        if inmate.get('posted') or not os.path.exists(d.get('Mugshot_File', '')):
            continue
        out = os.path.join(Config.REELS_DIR, os.path.basename(d['Mugshot_File']).rsplit('.', 1)[0] + '.mp4')
        try:
            reels.make_clip(out, 7, d['Mugshot_File'], d.get('Full Name', ''),
                            reels.charge_lines(d.get('Charge 1', ''), Config.CHARGE_SEPARATOR),
                            'MINNEAPOLIS MUGSHOTS')
            d['Reel_File'] = out
            print(f"🎬 Reel: {out}")
        except Exception as e:
            print(f"⚠️  Reel failed for {d.get('Full Name')}: {e}")

    # Top 5 recap: the queue is already ranked, so take the first five with photos, counting down to #1
    q['recap_file'], q['recap_posted_at'] = None, None
    top = [i['data'] for i in q['inmates'] if os.path.exists(i['data'].get('Mugshot_File', ''))][:5]
    if len(top) == 5:
        try:
            date = datetime.strptime(top[0].get('Booking_Date') or get_current_date(), "%m/%d/%Y")
            clips = [reels.make_clip(os.path.join(Config.REELS_DIR, '_intro.mp4'), 2,
                                     header=f"TOP 5 MUGSHOTS\n{date.strftime('%b %-d, %Y').upper()}")]
            for rank in range(5, 0, -1):
                d = top[rank - 1]
                clips.append(reels.make_clip(
                    os.path.join(Config.REELS_DIR, f'_rank{rank}.mp4'), 3, d['Mugshot_File'], d.get('Full Name', ''),
                    reels.charge_lines(d.get('Charge 1', ''), Config.CHARGE_SEPARATOR, max_lines=3), f"#{rank}"))
            q['recap_file'] = reels.concat(clips, os.path.join(Config.REELS_DIR, 'recap.mp4'))
            for c in clips:
                os.remove(c)
            q['recap'] = [{'Full Name': d.get('Full Name'), 'Charge 1': d.get('Charge 1')} for d in top]
            q['recap_date'] = date.strftime('%m/%d/%Y')
            print(f"🎬 Recap: {q['recap_file']}")
        except Exception as e:
            print(f"⚠️  Recap reel failed: {e}")

    with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(q, f, indent=2, ensure_ascii=False)

def post_recap(test_mode=False):
    """Post the Top 5 recap Reel once."""
    with open(Config.QUEUE_FILENAME, 'r', encoding='utf-8') as f:
        q = json.load(f)
    if not q.get('recap_file') or q.get('recap_posted_at'):
        print("📭 No recap to post")
        return False
    top = q['recap']
    lines = "\n".join(f"#{n}: {d['Full Name']} - {(d['Charge 1'] or '').split(Config.CHARGE_SEPARATOR)[0]}"
                      for n, d in enumerate(top, 1))
    caption = f"""TOP 5 MUGSHOTS - {q.get('recap_date', '')}

{lines}

Hennepin County, MN

{Config.DISCLAIMER}

#minneapolismugshots #HennepinCounty #Arrest #PublicRecord #Minnesota #Minneapolis"""
    print(caption)
    url = f"{Config.PAGES_URL}/{q['recap_file']}"
    if not post_to_instagram(url, caption, get_api_credentials(), test_mode, video_url=url):
        return False
    q['recap_posted_at'] = get_current_datetime_iso()
    with open(Config.QUEUE_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(q, f, indent=2, ensure_ascii=False)
    print("✅ Recap posted")
    return True

if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "test-instagram":
            test_instagram_posting()
        elif command == "post-next":
            # Post next inmate from queue
            post_next_inmates()
        elif command == "post-next-test":
            # Post next inmate in test mode (no actual posting)
            post_next_inmates(test_mode=True)
        elif command == "test":
            # Full scraping in test mode (limit to 25 inmates, filter to top 10 highest priority)
            print("🧪 Running in TEST MODE - processing 25 inmates, filtering to top 10 highest priority (charge + bail)")
            open_hennepin_jail_roster(inmate_limit=Config.TEST_INMATE_LIMIT)
        elif command in ("preflight", "check-posting-status"):
            mode, reason = posting_mode()
            print(f"mode={mode or 'none'} reason={reason}")
            if os.getenv('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as gh:
                    gh.write(f"mode={mode}\nreason={reason}\n")
        elif command == "make-reels":
            build_reels()
        elif command == "post-recap":
            post_recap()
        elif command == "post-recap-test":
            post_recap(test_mode=True)
        elif command == "check-queue":
            # Check posting queue status
            check_posting_queue()
        elif command == "cleanup-mugshots":
            # Clean up ALL mugshot files
            cleanup_all_mugshots()
        elif command == "cleanup-unposted":
            # Clean up unposted inmates' mugshots and prune queue
            cleanup_unposted_mugshots()
        elif command == "purge-unqueued":
            # Delete every mugshot not needed for an upcoming post
            purge_unqueued_mugshots()
        elif command == "cleanup-posted":
            # Clean up existing posted inmates' mugshots (legacy)
            cleanup_existing_posted_mugshots()
        else:
            print(f"Unknown command: {command}")
            print("Available commands:")
            print("  python data.py                # Full scraping (100 inmates) with top 10 highest priority filtering")
            print("  python data.py test           # Test scraping (25 inmates → top 10 highest priority)")
            print("  python data.py test-instagram # Test posting with existing data")
            print("  python data.py post-next      # Post next inmate from queue")
            print("  python data.py post-next-test # Test posting (simulation only)")
            print("  python data.py preflight      # What a posting run would do now (post / recap / nothing)")
            print("  python data.py make-reels     # Render Reels for the queue + Top 5 recap (needs ffmpeg)")
            print("  python data.py post-recap     # Post the Top 5 recap Reel")
            print("  python data.py check-queue    # Check posting queue status")
            print("  python data.py cleanup-mugshots # Clean up ALL mugshot files (repo + docs)")
            print("  python data.py cleanup-unposted # Clean up unposted inmates' mugshots and prune queue")
            print("  python data.py cleanup-posted   # Clean up only posted inmates' mugshots (legacy)")
            print("  python data.py purge-unqueued   # Delete all mugshots not needed for an upcoming post")
    else:
        # Production mode - scrape 100 inmates and filter to top 10 with highest priority
        print("🚀 Running in PRODUCTION MODE - processing 100 inmates, filtering to top 10 highest priority (charge + bail)")
        open_hennepin_jail_roster(inmate_limit=Config.DEFAULT_INMATE_LIMIT)

