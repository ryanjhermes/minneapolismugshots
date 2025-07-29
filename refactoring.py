import time
from datetime import datetime, timedelta
import csv
import base64
import os
import json
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import Select
from datetime import datetime
import pytz
import re
import sys

load_dotenv()

class Config:
    """Centralized configuration for the scraping application"""
    
    # Scraping settings
    DEFAULT_INMATE_LIMIT = 100
    TEST_INMATE_LIMIT = 25
    MODAL_WAIT_TIME = 5
    CLICK_WAIT_TIME = 3
    
    # Quality thresholds
    MIN_NAME_LENGTH = 3
    MAX_NAME_LENGTH = 50
    MIN_CHARGE_LENGTH = 5
    
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

def convert_base64_to_image(data_url, filename_prefix="mugshot"):
    """Convert base64 data URL to an actual image file in mugshots folder"""
    try:
        # Create mugshots directory if it doesn't exist
        mugshots_dir = "mugshots"
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

def input_date_field(driver, date_value, field_identifier="minDate"):
    """
    Input data into a date field
    
    Args:
        driver: Selenium WebDriver instance
        date_value: Date string in MM/DD/YYYY format
        field_identifier: How to identify the field (formcontrolname, id, etc.)
    """
    # Import selenium components needed for this function

    
    try:
        print(f"Looking for date field with identifier: {field_identifier}")
        
        # Try multiple ways to find the date input field
        date_input = None
        
        # Method 1: By formcontrolname attribute
        try:
            date_input = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'input[formcontrolname="{field_identifier}"]')))
            print("✅ Found date field by formcontrolname")
        except:
            pass
        
        if date_input:
            print(f"📍 Field info - Tag: {date_input.tag_name}, Type: {date_input.get_attribute('type')}")
            print(f"📍 Field attributes - ID: {date_input.get_attribute('id')}, Name: {date_input.get_attribute('formcontrolname')}")
            
            # Scroll to element and focus
            driver.execute_script("arguments[0].scrollIntoView(true);", date_input)
            time.sleep(0.5)
            
            # Convert MM/DD/YYYY to YYYY-MM-DD (HTML5 standard)
            month, day, year = date_value.split('/')
            html5_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            print(f"📍 Using HTML5 date format: {date_value} → {html5_date}")
            
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
                
            # Final check
            final_value = date_input.get_attribute('value')
            print(f"📍 Final field value: '{final_value}'")
            
        else:
            print("❌ Could not find the date input field")
            return False
            
    except Exception as e:
        print(f"❌ Error inputting date: {e}")
        return False
            
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
    
    def extract_all_fields(self):
        """Main extraction method that orchestrates all field extraction"""
        self.log("Starting field extraction...", "INFO")
        
        # Wait for modal to load
        time.sleep(Config.MODAL_WAIT_TIME)
        
        # Get page content
        page_text = self.driver.find_element(By.TAG_NAME, 'body').text
        self.log(f"Page content length: {len(page_text)} characters", "DEBUG")
        
        # Extract each field
        self._extract_name(page_text)
        self._extract_charge(page_text)
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
    
    def _extract_charge(self, page_text):
        """Extract primary charge using multiple strategies"""
        self.log("Extracting charge information...", "DEBUG")
        
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for charge patterns
            if line == 'Charge: 1':
                # Look for description in next few lines
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].strip() == 'Description:' and j + 1 < len(lines):
                        charge_desc = lines[j + 1].strip()
                        if self._is_valid_charge(charge_desc):
                            self.extracted_data['Charge 1'] = charge_desc
                            self.log(f"Found charge: {charge_desc}", "SUCCESS")
                            return
        
        self.log("No valid charge found", "WARNING")
    
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

def fill_form_with_current_date(driver, inmate_limit=25):
    def select_dropdown_option(driver, option_text="100", dropdown_type="results_per_page"):
        print(f"🔽 Looking for dropdown to select option: {option_text}")
        
        dropdown = None
        
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
        
        if dropdown:
            print(f"📍 Dropdown info - Tag: {dropdown.tag_name}, ID: {dropdown.get_attribute('id')}")
            
            # Scroll to dropdown and focus
            driver.execute_script("arguments[0].scrollIntoView(true);", dropdown)
            time.sleep(0.5)
            select = Select(dropdown)
            
            select.select_by_visible_text(option_text)
            print(f"✅ Selected by visible text: {option_text}")
            return True
    def get_current_date():
        central_tz = pytz.timezone('US/Central')
        central_time = datetime.now(central_tz)
        current_date = central_time.strftime("%m/%d/%Y")
        print(f"📅 Current date (Central Time): {current_date}")
        return current_date
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
            headers = ['Full Name', 'Charge 1', 'Bail', 'Mugshot_File']
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                
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
    def save_to_posting_queue(data_list):
        """Save inmates to posting queue for staggered posting"""

        def filter_priority_inmates(d, n=10):
            """Filter inmates by posting priority (charge + bail = higher priority)"""
            def get_priority(inmate):
                priority = 0
                # Charge: +1 priority point
                if inmate.get('Charge 1') and inmate['Charge 1'] != 'No charge listed':
                    priority += 1
                # Bail: +1 priority point
                if inmate.get('Bail') and inmate['Bail'] != 'No bail information':
                    priority += 1
                return priority
            
            # Sort by priority (highest first), then by bail amount for tie-breaking
            def get_bail_amount(bail_str):
                if not bail_str or bail_str == 'No bail information':
                    return 0
                # Extract dollar amount from bail string
                match = re.search(r'\$[\d,]+\.?\d*', bail_str)
                if match:
                    return float(match.group()[1:].replace(',', ''))
                return 0
            
            return sorted(d, key=lambda i: (-get_priority(i), -get_bail_amount(i.get('Bail', ''))))[:n]
        
        print(f"💾 Creating posting queue with {len(data_list)} inmates...")
        
        # Filter to top 10 highest priority inmates BEFORE creating queue
        filtered_inmates = filter_priority_inmates(data_list, n=10)
        
        # Add timestamp and posting status to each inmate
        central_tz = pytz.timezone('US/Central')
        central_time = datetime.now(central_tz)
        iso = central_time.isoformat()
        queue_data = {
            'created_at': iso,
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
        print(f"🎯 Prioritized from {len(data_list)} total inmates to top 10 by posting priority (charge + bail)")

        return True

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
        headers = ['Full Name', 'Charge 1', 'Bail', 'Mugshot_File']
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            
            # Write header
            writer.writeheader()
            
            # Write data rows
            for data in extracted_data_list:
                writer.writerow(data)
                
        
        if success_save:
            print(f"\n🎉 SUCCESS! Quality inmates (with mugshots + charges) saved to {filename}")
            print(f"\n📊 SUMMARY - READY FOR POSTING:")
            for i, data in enumerate(extracted_data_list, 1):
                mugshot_info = data.get('Mugshot_File', 'N/A')
                print(f"   {i}. {data.get('Full Name', 'N/A')} - {data.get('Charge 1', 'N/A')} - {data.get('Bail', 'N/A')} - Image: {mugshot_info}")
            
            # Save to posting queue (this will now filter to top 10 highest bail)
            print(f"\n📋 Saving quality inmates to posting queue...")
            queue_success = save_to_posting_queue(extracted_data_list)
            
            if queue_success:
                print(f"\n🚀 COMPLETE SUCCESS! Data scraped, filtered to TOP 10 HIGHEST BAIL, and queued for posting!")
                print(f"📅 Top 10 inmates will be posted every 15 minutes starting at 6:00 PM Central")
                print(f"🎲 Random delays added to avoid Instagram automation detection")
            else:
                print(f"\n⚠️  Data scraped and saved, but failed to create posting queue")
        else:
            print(f"\n⚠️  Data extracted but failed to save to CSV")
    else:
        print(f"\n❌ No data extracted from booking IDs")
    
    return success_min or success_max

def open_hennepin_jail_roster(inmate_limit=Config.DEFAULT_INMATE_LIMIT):
    """
    Opens the Hennepin County jail roster website using Selenium
    
    Args:
        inmate_limit: Maximum number of inmates to process (default 100 for production)
    """
    # Import selenium only when needed for scraping

    
    # Set up ChromeDriver service
    service = Service(ChromeDriverManager().install())
    
    # Configure Chrome options
    options = webdriver.ChromeOptions()
    
    # Check if running in CI environment (GitHub Actions)
    is_ci = os.getenv('CI') or os.getenv('GITHUB_ACTIONS')
    
    if is_ci:
        print("🤖 Running in CI environment - using headless mode")
        options.add_argument('--headless=new')  # Use new headless mode
    
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
                print(f"\n📋 Next {min(2, pending)} inmates to post:")
                unposted = [inmate for inmate in queue_data['inmates'] if not inmate['posted']]
                for i, inmate in enumerate(unposted[:2], 1):
                    name = inmate['data'].get('Full Name', 'Unknown')
                    print(f"   {i}. {name}")
            else:
                print("✅ All inmates have been posted!")
                
        except FileNotFoundError:
            print("📭 No posting queue found")
            print("💡 Run 'python data.py' to create a queue")
            
    except Exception as e:
        print(f"❌ Error checking queue: {e}")

open_hennepin_jail_roster(inmate_limit=Config.DEFAULT_INMATE_LIMIT)