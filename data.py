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
        
        # Single consistent caption format (without charge field)
        caption = f"""
NAME: {name}
BAIL: {bail}

Arrest Date: {get_current_date()}
Hennepin County, MN

#minneapolismugshots #HennepinCounty #Arrest #PublicRecord #Minnesota #Minneapolis"""
        
        return caption
        
    except Exception as e:
        print(f"❌ Error generating caption: {e}")
        return f"🚨 Minneapolis Arrest Alert - {data.get('Full Name', 'Unknown')}"

def post_to_instagram(image_url, caption, credentials, test_mode=False):
    """Post image to Instagram using Meta API"""
    try:
        access_token = credentials['access_token']
        business_id = credentials['business_id']
        
        if not access_token or not business_id:
            print("❌ Missing Meta API credentials")
            return False
        
        # Test mode - just simulate posting
        if test_mode:
            print(f"🧪 TEST MODE - Would post to Instagram:")
            print(f"   📸 Image: {image_url}")
            print(f"   📝 Caption: {caption[:100]}...")
            print(f"   🎯 Business ID: {business_id}")
            print(f"✅ TEST MODE - Post simulation successful")
            return True
        
        # Step 1: Create media object
        print(f"📸 Creating Instagram media for: {image_url}")
        
        media_url = f"https://graph.facebook.com/v23.0/{business_id}/media"
        media_params = {
            'image_url': image_url,
            'caption': caption,
            'access_token': access_token
        }
        
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
    Filter inmates to only include the top N highest bail amounts
    Excludes inmates with "No Bail Information" - only includes actual bail amounts
    
    Args:
        data_list: List of inmate dictionaries
        top_n: Number of top inmates to return (default 10)
    
    Returns:
        List of top N inmates sorted by bail amount (highest first)
    """
    try:
        print(f"\n🔍 Filtering to top {top_n} highest bail inmates (excluding 'No Bail Information')...")
        
        if not data_list:
            print("❌ No inmates to filter")
            return []
        
        # Add parsed bail amount to each inmate for sorting, excluding "No Bail Information"
        inmates_with_bail = []
        excluded_count = 0
        
        for inmate in data_list:
            bail_str = inmate.get('Bail', '')
            bail_amount = parse_bail_amount(bail_str)
            
            # Exclude inmates with "No Bail Information" or zero bail
            if 'No Bail Information' in bail_str or bail_amount <= 0:
                excluded_count += 1
                print(f"⏭️  EXCLUDING: {inmate.get('Full Name', 'Unknown')}: {bail_str} (no bail info)")
                continue
            
            inmates_with_bail.append({
                **inmate,
                '_bail_amount': bail_amount
            })
            
            print(f"📊 {inmate.get('Full Name', 'Unknown')}: {bail_str} → ${bail_amount:,.2f}")
        
        print(f"\n📊 Excluded {excluded_count} inmates with no bail information")
        print(f"📊 {len(inmates_with_bail)} inmates with actual bail amounts available for ranking")
        
        # Sort by bail amount (highest first)
        sorted_inmates = sorted(inmates_with_bail, key=lambda x: x['_bail_amount'], reverse=True)
        
        # Take top N and remove the temporary _bail_amount field
        top_inmates = []
        for i, inmate in enumerate(sorted_inmates[:top_n]):
            # Remove the temporary sorting field
            filtered_inmate = {k: v for k, v in inmate.items() if k != '_bail_amount'}
            top_inmates.append(filtered_inmate)
            
            bail_amount = inmate['_bail_amount']
            if bail_amount == 999999999:
                bail_display = "NO BAIL"
            else:
                bail_display = f"${bail_amount:,.2f}"
            
            print(f"🏆 #{i+1}: {inmate.get('Full Name', 'Unknown')} - {bail_display}")
        
        print(f"\n✅ Filtered from {len(data_list)} to {len(top_inmates)} highest bail inmates")
        return top_inmates
        
    except Exception as e:
        print(f"❌ Error filtering top bail inmates: {e}")
        return data_list  # Return original list on error

def save_to_posting_queue(data_list):
    """Save inmates to posting queue for staggered posting"""
    try:
        print(f"💾 Creating posting queue with {len(data_list)} inmates...")
        
        # Filter to top 10 highest bail inmates BEFORE creating queue
        filtered_inmates = filter_top_bail_inmates(data_list, top_n=10)
        
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
        with open('posting_queue.json', 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Posting queue saved successfully")
        print(f"📊 Queue stats: {len(filtered_inmates)} TOP BAIL inmates ready for posting")
        print(f"🎯 Filtered from {len(data_list)} total inmates to top 10 highest bail")
        return True
        
    except Exception as e:
        print(f"❌ Error saving posting queue: {e}")
        return False

def get_next_inmates_to_post(batch_size=2):
    """Get next batch of inmates to post from queue"""
    try:
        # Load queue
        try:
            with open('posting_queue.json', 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
        except FileNotFoundError:
            print("📭 No posting queue found")
            return []
        
        # Find unposted inmates
        unposted_inmates = [inmate for inmate in queue_data['inmates'] if not inmate['posted']]
        
        if not unposted_inmates:
            print("✅ All inmates have been posted!")
            return []
        
        # Get next batch
        next_batch = unposted_inmates[:batch_size]
        
        print(f"📋 Found {len(next_batch)} inmates ready to post")
        print(f"📊 Remaining in queue: {len(unposted_inmates)} total")
        
        return next_batch
        
    except Exception as e:
        print(f"❌ Error reading posting queue: {e}")
        return []

def mark_inmates_as_posted(inmate_ids):
    """Mark inmates as posted in the queue"""
    try:
        # Load queue
        with open('posting_queue.json', 'r', encoding='utf-8') as f:
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
        with open('posting_queue.json', 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Marked {posted_count} inmates as posted")
        print(f"📊 Total posted: {queue_data['posted_count']}/{queue_data['total_inmates']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating posting queue: {e}")
        return False

def post_next_inmates(batch_size=2, repo_name="minneapolismugshots", username="ryanjhermes", test_mode=False):
    """Post next batch of inmates from queue"""
    try:
        print(f"\n📱 Starting batch Instagram posting...")
        
        # Get next inmates to post
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
                
                # Post to Instagram
                success = post_to_instagram(image_url, caption, credentials, test_mode)
                
                if success:
                    successful_posts.append(inmate_id)
                    print(f"✅ Successfully posted {inmate_data.get('Full Name', 'Unknown')}")
                else:
                    failed_posts.append(inmate_id)
                    print(f"❌ Failed to post {inmate_data.get('Full Name', 'Unknown')}")
                
                # Randomized wait between posts in the same batch (human-like behavior)
                if len(inmates_to_post) > 1 and inmate != inmates_to_post[-1]:
                    import random
                    # Random delay between 8-15 seconds instead of fixed 10 seconds
                    random_delay = random.randint(8, 15)
                    print(f"⏳ Waiting {random_delay} seconds before next post (randomized for detection avoidance)...")
                    time.sleep(random_delay)
                
            except Exception as e:
                print(f"❌ Error processing inmate #{inmate_id}: {e}")
                failed_posts.append(inmate_id)
                continue
        
        # Mark successful posts as completed
        if successful_posts:
            mark_inmates_as_posted(successful_posts)
        
        # Summary
        print(f"\n📊 BATCH POSTING SUMMARY:")
        print(f"   ✅ Successful posts: {len(successful_posts)}")
        print(f"   ❌ Failed posts: {len(failed_posts)}")
        print(f"   📱 Total in batch: {len(inmates_to_post)}")
        
        return len(successful_posts) > 0
        
    except Exception as e:
        print(f"❌ Error in batch posting process: {e}")
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
    """
    # Import selenium components needed for this function
    from selenium.webdriver.common.by import By
    
    try:
        print("\n📋 Extracting key details (Full Name, Charge 1, Bail, Mugshot)...")
        
        # Wait for modal to fully load - longer wait for CI environment
        time.sleep(5)
        
        extracted_data = {
            'Full Name': '',
            'Charge 1': '',
            'Bail': '',
            'Mugshot_File': ''
        }
        
        # First, try to get the name from the main page before modal
        try:
            # Look for name in the main page content
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            page_lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            
            # Look for name patterns in the page content
            name_patterns = [
                'Full Name:',
                'Name:',
                'Inmate Name:',
                'Arrestee Name:',
                'Defendant Name:'
            ]
            
            for pattern in name_patterns:
                for i, line in enumerate(page_lines):
                    if pattern in line and i + 1 < len(page_lines):
                        potential_name = page_lines[i + 1]
                        # Check if it looks like a name (contains letters and spaces)
                        if (potential_name and 
                            any(c.isalpha() for c in potential_name) and 
                            ' ' in potential_name and
                            len(potential_name) > 5):
                            extracted_data['Full Name'] = potential_name
                            print(f"✅ Found Full Name from page: {extracted_data['Full Name']}")
                            break
                if extracted_data['Full Name']:
                    break
        except Exception as e:
            print(f"⚠️  Error extracting name from page: {e}")
        
        # Find the modal content
        modal_content = None
        modal_selectors = [
            '[role="dialog"]',
            '.modal',
            '[class*="modal"]',
            '[class*="dialog"]'
        ]
        
        for selector in modal_selectors:
            try:
                modal_content = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"✅ Found modal with selector: {selector}")
                
                # Wait for modal to be fully loaded and interactive
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    print("✅ Modal is fully loaded and interactive")
                except Exception as e:
                    print(f"⚠️  Modal wait timeout: {e}")
                
                break
            except:
                continue
        
        if modal_content:
            # Try to get modal content with retries for CI environment
            modal_text = ""
            max_retries = 3
            for attempt in range(max_retries):
                modal_text = modal_content.text
                lines = [line.strip() for line in modal_text.split('\n') if line.strip()]
                
                # Check if we have enough content (should have more than just headers)
                if len(lines) > 20:  # Should have substantial content
                    print(f"✅ Modal content loaded successfully (attempt {attempt + 1})")
                    break
                else:
                    print(f"⚠️  Modal content seems incomplete (attempt {attempt + 1}), waiting...")
                    time.sleep(2)
            
            # Debug: Print all modal lines for this inmate
            print("\n--- MODAL LINES ---")
            for idx, line in enumerate(lines):
                print(f"{idx:2d}: {line}")
            print("--- END MODAL LINES ---\n")

            # Extract Full Name from modal if not already found
            if not extracted_data['Full Name']:
                # Look for name patterns in modal
                name_patterns = [
                    'Full Name:',
                    'Name:',
                    'Inmate Name:',
                    'Arrestee Name:',
                    'Defendant Name:',
                    'Subject Name:'
                ]
                
                for pattern in name_patterns:
                    for i, line in enumerate(lines):
                        if pattern in line:
                            if i + 1 < len(lines):
                                potential_name = lines[i + 1]
                                # Check if it looks like a name (contains letters and spaces)
                                if (potential_name and 
                                    any(c.isalpha() for c in potential_name) and 
                                    ' ' in potential_name and
                                    len(potential_name) > 5):
                                    extracted_data['Full Name'] = potential_name
                                    print(f"✅ Found Full Name from modal: {extracted_data['Full Name']}")
                                    break
                    if extracted_data['Full Name']:
                        break
                
                # If still no name, look for any line that looks like a name (contains letters, spaces, and is reasonably long)
                if not extracted_data['Full Name']:
                    for line in lines:
                        # Look for lines that look like names (contains letters, spaces, and reasonable length)
                        if (line and 
                            any(c.isalpha() for c in line) and 
                            ' ' in line and
                            len(line) > 8 and len(line) < 50 and
                            not any(keyword in line.upper() for keyword in ['CASE', 'CHARGE', 'BAIL', 'COURT', 'DATE', 'TIME', 'STATUTE', 'DESCRIPTION'])):
                            # Additional check: should contain at least one uppercase letter (likely a name)
                            if any(c.isupper() for c in line):
                                extracted_data['Full Name'] = line
                                print(f"✅ Found potential name from modal content: {extracted_data['Full Name']}")
                                break

            # Extract first charge description
            charge_found = False
            for i, line in enumerate(lines):
                if line == 'Charge: 1':
                    print(f"[DEBUG] Found 'Charge: 1' at line {i}")
                    for j in range(i + 1, min(i + 15, len(lines))):
                        print(f"[DEBUG] Checking line {j}: '{lines[j]}'")
                        if lines[j] == 'Description:':
                            print(f"[DEBUG] Found 'Description:' at line {j}")
                            if j + 1 < len(lines):
                                charge_desc = lines[j + 1]
                                print(f"[DEBUG] Next line ({j+1}) contains: '{charge_desc}'")
                                if not charge_desc.endswith(':') and len(charge_desc) > 3:
                                    extracted_data['Charge 1'] = charge_desc
                                    print(f"✅ Found Charge 1: {extracted_data['Charge 1']}")
                                    charge_found = True
                                    break
                            else:
                                print(f"[DEBUG] No line after 'Description:' at line {j}")
                    if charge_found:
                        break
            if not extracted_data['Charge 1']:
                print("🔄 Using keyword fallback for charge...")
                charge_keywords = ['ASSAULT', 'THEFT', 'BURGLARY', 'DWI', 'DOMESTIC', 'DRUG', 'WARRANT', 'VIOLATION', 'DRIVING', 'POSSESSION', 'WEAPONS', 'TRAFFIC']
                for i, line in enumerate(lines):
                    if (any(keyword in line.upper() for keyword in charge_keywords) and 
                        not line.endswith(':') and 
                        len(line) > 10):
                        extracted_data['Charge 1'] = line
                        print(f"✅ Found charge via keyword fallback: {extracted_data['Charge 1']}")
                        break
                
                # If still no charge, try to extract from case details section
                if not extracted_data['Charge 1']:
                    print("🔄 Looking for charge in case details section...")
                    for i, line in enumerate(lines):
                        if 'Case Details' in line and i + 1 < len(lines):
                            # Look for charge-like content in the next few lines
                            for j in range(i + 1, min(i + 10, len(lines))):
                                potential_charge = lines[j]
                                if (potential_charge and 
                                    not potential_charge.endswith(':') and 
                                    len(potential_charge) > 10 and
                                    any(keyword in potential_charge.upper() for keyword in charge_keywords)):
                                    extracted_data['Charge 1'] = potential_charge
                                    print(f"✅ Found charge in case details: {extracted_data['Charge 1']}")
                                    break
                            if extracted_data['Charge 1']:
                                break
            if not extracted_data['Charge 1']:
                extracted_data['Charge 1'] = 'No valid charge found'
                print(f"⚠️  No charge found - using default: {extracted_data['Charge 1']}")
            # Print the final extracted charge for debugging
            print(f"[DEBUG] Final extracted charge: {extracted_data['Charge 1']}")
            
            # Set default if still empty
            if not extracted_data['Charge 1']:
                extracted_data['Charge 1'] = 'No valid charge found'
                print(f"⚠️  No charge found - using default: {extracted_data['Charge 1']}")
            
            # Extract Bail information with better logic
            for i, line in enumerate(lines):
                if 'Bail Options:' in line:
                    if i + 1 < len(lines):
                        bail_candidate = lines[i + 1]
                        # Only accept if it contains dollar sign or specific bail keywords
                        if ('$' in bail_candidate or 
                            'NO BAIL' in bail_candidate.upper() or
                            'RELEASED' in bail_candidate.upper() or
                            'BOND' in bail_candidate.upper()):
                            extracted_data['Bail'] = bail_candidate
                            print(f"✅ Found Bail: {extracted_data['Bail']}")
                        break
            
            # If no specific "Bail Options:" found, look for dollar amounts
            if not extracted_data['Bail']:
                for line in lines:
                    if '$' in line and ('BAIL' in line.upper() or 'BOND' in line.upper()):
                        extracted_data['Bail'] = line
                        print(f"✅ Found Bail (alternative): {extracted_data['Bail']}")
                        break
            
            # If still no bail found, mark as "No Bail Information"
            if not extracted_data['Bail']:
                extracted_data['Bail'] = 'No Bail Information'
                print(f"⚠️  No bail information found, marked as: {extracted_data['Bail']}")
            
            # Extract mugshot image
            try:
                print("\n🖼️  Looking for mugshot image...")
                # Look for image elements in the modal
                img_elements = modal_content.find_elements(By.CSS_SELECTOR, 'img')
                mugshot_saved = False
                
                for img in img_elements:
                    src = img.get_attribute('src')
                    alt = img.get_attribute('alt') or ""
                    
                    # Check if this looks like a booking photo
                    if (src and 
                        ('data:image' in src or 'booking' in alt.lower() or 'photo' in alt.lower() or 'mugshot' in alt.lower())):
                        
                        print(f"📸 Found potential mugshot: {alt}")
                        
                        # Use full name for filename if available
                        if extracted_data['Full Name']:
                            # Clean filename (remove special characters)
                            clean_name = "".join(c for c in extracted_data['Full Name'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                            clean_name = clean_name.replace(' ', '_')
                            filename_prefix = f"mugshot_{clean_name}"
                        else:
                            filename_prefix = f"mugshot_{int(time.time())}"
                        
                        # Convert and save the image
                        saved_filename = convert_base64_to_image(src, filename_prefix)
                        if saved_filename:
                            extracted_data['Mugshot_File'] = saved_filename
                            mugshot_saved = True
                            break
                
                if not mugshot_saved:
                    print("⚠️  No mugshot image found or saved")
                    extracted_data['Mugshot_File'] = 'No Image'
                    
            except Exception as e:
                print(f"❌ Error extracting mugshot: {e}")
                extracted_data['Mugshot_File'] = 'Error'
            
            print(f"\n📊 EXTRACTED DATA:")
            print(f"   Full Name: {extracted_data['Full Name']}")
            print(f"   Charge 1: {extracted_data['Charge 1']}")
            print(f"   Bail: {extracted_data['Bail']}")
            print(f"   Mugshot File: {extracted_data['Mugshot_File']}")
            
        else:
            print("❌ Could not find modal content")
            
        return extracted_data
        
    except Exception as e:
        print(f"❌ Error extracting key details: {e}")
        return extracted_data

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

def save_to_csv(data_list, filename="jail_roster_data.csv"):
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
    Process multiple booking IDs and extract data from each
    """
    try:
        print(f"\n🔄 Processing multiple bookings (limit: {limit})...")
        
        # Get all booking IDs
        booking_ids = get_all_booking_ids(driver, limit)
        
        if not booking_ids:
            print("❌ No booking IDs found")
            return []
        
        all_extracted_data = []
        
        for i, booking_info in enumerate(booking_ids):
            try:
                booking_element = booking_info['element']
                booking_id = booking_info['id']
                
                print(f"\n{'='*50}")
                print(f"🔄 Processing booking {i+1}/{len(booking_ids)}: {booking_id}")
                print(f"{'='*50}")
                
                # Scroll to element and highlight briefly
                driver.execute_script("arguments[0].scrollIntoView(true);", booking_element)
                time.sleep(0.5)
                
                # Highlight the element
                try:
                    driver.execute_script("arguments[0].style.border='3px solid blue';", booking_element)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].style.border='';", booking_element)
                except:
                    pass
                
                # Click the booking ID
                print(f"🖱️  Clicking booking ID: {booking_id}")
                booking_element.click()
                time.sleep(3)
                
                # Extract key details
                extracted_data = extract_key_details(driver)
                
                # If no name was found, use booking ID as fallback
                if not extracted_data['Full Name']:
                    extracted_data['Full Name'] = f"Booking_{booking_id}"
                    print(f"⚠️  No name found, using booking ID as fallback: {extracted_data['Full Name']}")
                
                # Don't add Booking ID to match CSV headers exactly
                
                if extracted_data['Full Name']:  # Only add if we got some data
                    # Check if inmate has required data (mugshot and valid bail - charge is optional)
                    has_mugshot = extracted_data.get('Mugshot_File') and extracted_data.get('Mugshot_File') != 'No Image'
                    charge_text = extracted_data.get('Charge 1', '').strip()
                    bail_text = extracted_data.get('Bail', '').strip()

                    # Define invalid charge patterns that should be filtered out
                    invalid_charges = [
                        'No valid charge found',
                        'Charge information not available', 
                        'Severity of Charge:',
                        'Description:',
                        'Charge Status:',
                        'No charge listed'
                    ]
                    # Prevent charge from being set to the inmate's name
                    is_charge_name = (charge_text.lower() == extracted_data['Full Name'].lower())
                    has_valid_charge = (charge_text and 
                                       not charge_text.endswith(':') and 
                                       charge_text not in invalid_charges and
                                       len(charge_text) > 5 and
                                       not is_charge_name)

                    # Define invalid bail patterns
                    invalid_bails = [
                        '',
                        'No Bail Information',
                        'NO BAIL INFORMATION',
                        'NO BAIL',
                        'HOLD WITHOUT BAIL',
                        'RELEASED',
                        'NO BAIL REQUIRED',
                        'No bail information',
                        'No bail',
                        'No Bail',
                        'No bail required',
                    ]
                    # Accept any bail with a dollar sign, but reject $0.00 or NO BAIL REQUIRED
                    bail_text_upper = bail_text.upper()
                    has_valid_bail = (
                        ('$' in bail_text) and
                        ('$0.00' not in bail_text_upper) and
                        ('NO BAIL REQUIRED' not in bail_text_upper) and
                        not any(bail_text.strip().upper() == b.upper() for b in invalid_bails)
                    )

                    # Make charge field optional - only require mugshot and valid bail
                    if has_mugshot and has_valid_bail:
                        all_extracted_data.append(extracted_data)
                        print(f"✅ ACCEPTED: {extracted_data['Full Name']} - {charge_text} - {bail_text}")
                    else:
                        missing = []
                        if not has_mugshot: missing.append("mugshot")
                        if not has_valid_bail: missing.append(f"valid bail (got: '{bail_text}')")
                        print(f"⏭️  REJECTED: {extracted_data['Full Name']} - Missing: {', '.join(missing)}")
                else:
                    print(f"⚠️  No data extracted for {booking_id}")
                
                # Close the modal
                close_modal(driver)
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Error processing booking {booking_id}: {e}")
                # Try to close modal anyway
                close_modal(driver)
                continue
        
        print(f"\n📊 PROCESSING COMPLETE:")
        print(f"   Total IDs processed: {len(booking_ids)}")
        print(f"   Inmates with mugshot + valid bail: {len(all_extracted_data)}")
        print(f"   Filtered out (no mugshot or valid bail): {len(booking_ids) - len(all_extracted_data)}")
        
        return all_extracted_data
        
    except Exception as e:
        print(f"❌ Error processing multiple bookings: {e}")
        return []

def fill_form_with_current_date(driver, inmate_limit=25):
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

def open_hennepin_jail_roster(inmate_limit=100):
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

def test_instagram_posting():
    """Test Instagram posting with existing CSV data"""
    try:
        print("🧪 Testing Instagram posting with existing data...")
        
        # Read existing CSV data
        import csv
        data_list = []
        
        try:
            with open('jail_roster_data.csv', 'r', encoding='utf-8') as csvfile:
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
            print("❌ jail_roster_data.csv not found. Run scraping first.")
        except Exception as e:
            print(f"❌ Error reading CSV: {e}")
            
    except Exception as e:
        print(f"❌ Error in test: {e}")

def check_posting_queue():
    """Check status of posting queue"""
    try:
        print("📋 Checking posting queue status...")
        
        try:
            with open('posting_queue.json', 'r', encoding='utf-8') as f:
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

if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "test-instagram":
            test_instagram_posting()
        elif command == "post-next":
            # Post next batch of inmates from queue
            post_next_inmates()
        elif command == "post-next-test":
            # Post next batch in test mode (no actual posting)
            post_next_inmates(test_mode=True)
        elif command == "test":
            # Full scraping in test mode (limit to 25 inmates, filter to top 10 highest bail)
            print("🧪 Running in TEST MODE - processing 25 inmates, filtering to top 10 highest bail (excluding 'No Bail Information')")
            open_hennepin_jail_roster(inmate_limit=25)
        elif command == "check-queue":
            # Check posting queue status
            check_posting_queue()
        else:
            print(f"Unknown command: {command}")
            print("Available commands:")
            print("  python data.py                # Full scraping (100 inmates) with top 10 highest bail filtering")
            print("  python data.py test           # Test scraping (25 inmates → top 10 highest bail)")
            print("  python data.py test-instagram # Test posting with existing data")
            print("  python data.py post-next      # Post next batch from queue")
            print("  python data.py post-next-test # Test posting (simulation only)")
            print("  python data.py check-queue    # Check posting queue status")
    else:
        # Production mode - scrape 100 inmates and filter to top 10 with actual bail amounts
        print("🚀 Running in PRODUCTION MODE - processing 100 inmates, filtering to top 10 highest bail (excluding 'No Bail Information')")
        open_hennepin_jail_roster(inmate_limit=100)

