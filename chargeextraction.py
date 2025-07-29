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

# Selenium imports are moved to functions that need them to avoid import errors
# in workflows that only need posting functionality

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
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    
    try:
        print("\n📋 Extracting key details (Full Name, Charge 1, Bail, Mugshot)...")
        
        # Wait for modal to fully load - longer wait for CI environment
        time.sleep(5)

        # Initialize data structure
        extracted_data = {
            'Full Name': '',
            'Charge 1': '',
            'Bail': '',
            'Mugshot_File': 'No Image'  # Default, will be updated if mugshot found
        }

        try:
            # Look for name in the main page content
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            print("📍 Full page text:")
            # print(page_text)
            
            # Extract modal content between boundaries
            modal_start = "Beginning of modal content"
            modal_end = "End of modal content"
            
            if modal_start in page_text and modal_end in page_text:
                start_idx = page_text.find(modal_start) + len(modal_start)
                end_idx = page_text.find(modal_end)
                modal_content = page_text[start_idx:end_idx].strip()
                
                print(f"\n📋 Modal content extracted:")
                print(modal_content)
                
                # Parse the modal content line by line
                lines = [line.strip() for line in modal_content.split('\n') if line.strip()]
                
                print(f"\n🔍 Parsing {len(lines)} lines...")
                
                # Extract specific fields
                for i, line in enumerate(lines):
                    print(f"   {i+1:2d}. {line}")
                    
                    # Extract Full Name (line after "Full Name:")
                    if line == "Full Name:" and i + 1 < len(lines):
                        extracted_data['Full Name'] = lines[i + 1]
                        print(f"✅ Found Full Name: {lines[i + 1]}")
                    
                    # Extract Age (line after "Age:")
                    elif line == "Age:" and i + 1 < len(lines):
                        age = lines[i + 1]
                        print(f"✅ Found Age: {age}")
                    
                    # Extract Charge Description (line after "Charge: 1" and "Description:")
                    elif line == "Charge: 1" and i + 2 < len(lines):
                        # Look for "Description:" in the next few lines
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if lines[j] == "Description:" and j + 1 < len(lines):
                                extracted_data['Charge 1'] = lines[j + 1]
                                print(f"✅ Found Charge 1: {lines[j + 1]}")
                                break
                    
                    # Extract Bail information (look for bail-related fields)
                    elif "Bail" in line and ":" in line:
                        # Extract the value after the colon
                        if ":" in line:
                            bail_label, bail_value = line.split(":", 1)
                            if bail_value.strip():
                                extracted_data['Bail'] = bail_value.strip()
                                print(f"✅ Found Bail: {bail_value.strip()}")
                
                # Look for mugshot image
                try:
                    # Look for img elements that might be mugshots
                    img_elements = driver.find_elements(By.CSS_SELECTOR, 'img')
                    for img in img_elements:
                        src = img.get_attribute('src')
                        if src and ('mugshot' in src.lower() or 'photo' in src.lower() or 'image' in src.lower()):
                            # Convert base64 image to file
                            if src.startswith('data:image'):
                                filename = f"mugshot_{extracted_data['Full Name'].replace(' ', '_').replace(',', '')}.jpg"
                                filepath = convert_base64_to_image(src, filename)
                                if filepath:
                                    extracted_data['Mugshot_File'] = filepath
                                    print(f"✅ Found and saved mugshot: {filepath}")
                            break
                except Exception as e:
                    print(f"⚠️  Error looking for mugshot: {e}")
                
            else:
                print("❌ Could not find modal boundaries in page text")
                
        except Exception as e:
            print(f"❌ Error extracting page text: {e}")
        
        # Print final extracted data
        print(f"\n📊 EXTRACTED DATA:")
        for key, value in extracted_data.items():
            print(f"   {key}: {value}")
        
        return extracted_data
        
    except Exception as e:
        print(f"❌ Error in extract_key_details: {e}")
        return {
            'Full Name': '',
            'Charge 1': '',
            'Bail': '',
            'Mugshot_File': 'No Image'
        }

def fill_form_with_current_date(driver, inmate_limit=25):
    """
    Fill the form, process multiple booking IDs, and save to CSV with top 10 highest bail filter
    """
    print("\n🗓️  Using current date for form input...")
    central_tz = pytz.timezone('US/Central')
    central_time = datetime.now(central_tz)
    current_date = central_time.strftime("%m/%d/%Y")
    print(f"📅 Current date (Central Time): {current_date}")
    return current_date
    
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
        filename = "jail_roster_data.csv"
        
        success_save = save_to_csv(extracted_data_list, filename)
        
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

def run(inmate_limit=100):
    """
    Opens the Hennepin County jail roster website using Selenium
    
    Args:
        inmate_limit: Maximum number of inmates to process (default 100 for production)
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
        driver.get("https://jailroster.hennepin.us/")
        
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

run(inmate_limit=100)