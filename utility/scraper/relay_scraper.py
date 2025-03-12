#!/usr/bin/env python3
"""
Relay Scraper - A tool to scrape relay information from next.nostr.watch/relays

This script uses Selenium to automate a browser, navigate to the next.nostr.watch/relays
website, and extract relay URLs from all pages. It handles pagination and saves the
results to a file.
"""

import os
import time
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

def setup_browser_options():
    """Configure browser options for headless operation"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return options

def scroll_page(driver, pause=1.0):
    """Scroll down the page to ensure all content is loaded"""
    # Get scroll height
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # Wait to load page
        time.sleep(pause)
        
        # Calculate new scroll height and compare with last scroll height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    
    # Scroll back to top
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(pause)
    
    print("Scrolled through the page")

def wait_for_content(driver, timeout=60):
    """Wait for the relay content to load on the page"""
    try:
        # First, wait for the loading screen to disappear or complete
        try:
            # Wait for the loading progress to reach 100% or disappear
            WebDriverWait(driver, timeout).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".loading-indicator, .progress-bar"))
            )
            print("Loading screen disappeared")
        except:
            print("No loading indicator found or it didn't disappear in time")
        
        # Then wait a bit more for content to stabilize
        time.sleep(10)
        
        # Scroll through the page to ensure all content is loaded
        scroll_page(driver)
        
        # Take a screenshot of the current state
        driver.save_screenshot("page_current_state.png")
        print("Saved screenshot of current page state to page_current_state.png")
        
        # Now try to find table rows or any elements that might contain relay information
        selectors = [
            "table tr",  # Any table row
            "tbody tr",  # Table body rows
            "[class*='relay']",  # Any element with 'relay' in its class
            "[class*='row']",  # Any element with 'row' in its class
            "div[role='row']",  # ARIA role for rows
            "div[role='gridcell']",  # ARIA role for cells
            "div[class*='cell']",  # Any div with 'cell' in its class
            "a[href]"  # Any link
        ]
        
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                print(f"Found {len(elements)} elements with selector: {selector}")
                return True
        
        # If we get here, we couldn't find any of the expected elements
        print("Could not find relay elements with known selectors")
        
        # Check if we're still on a loading screen
        page_source = driver.page_source.lower()
        if "loading" in page_source or "booting" in page_source:
            print("Page appears to still be loading")
        
        return True  # Return True anyway to let the script try to extract relays
    except TimeoutException:
        print("Timed out waiting for content to load")
        # Return True anyway to let the script try to extract relays
        return True

def extract_relays_from_page(driver):
    """Extract relay URLs from the current page"""
    relays = []
    
    # Based on the screenshot, we can see the relay URLs are in the first column of a table
    # Let's try multiple approaches to extract them
    
    # Approach 1: Try to find all elements that might be relay URLs based on the screenshot
    try:
        # From the screenshot, we can see the relay URLs are in a table with a dark background
        # They appear to be in the first column
        
        # First, try to find all elements that might contain text that looks like a relay URL
        all_elements = driver.find_elements(By.XPATH, "//*")
        
        for element in all_elements:
            try:
                text = element.text.strip()
                
                # Skip empty text or very short text
                if not text or len(text) < 5:
                    continue
                
                # Skip text that doesn't look like a domain
                if not ("." in text and "/" in text) and not any(tld in text for tld in [".com", ".net", ".io", ".org", ".xyz", ".ai", ".online", ".me"]):
                    continue
                
                # Skip common non-relay URLs
                if any(skip in text.lower() for skip in ["googleapis", "gstatic", "w3.org", "jquery", "bootstrap", "font"]):
                    continue
                
                # If it looks like a relay URL but doesn't have wss://, add it
                if not text.startswith("wss://"):
                    # Check if it's just a domain with a trailing slash
                    if text.count("/") == 1 and text.endswith("/"):
                        url = f"wss://{text}"
                    else:
                        # Skip this, it's probably not a relay URL
                        continue
                else:
                    url = text
                
                # Basic validation
                if "." in url and "/" in url and len(url) > 10:
                    if url not in relays:
                        relays.append(url)
                        print(f"Found relay from element text: {url}")
            except:
                continue
    except Exception as e:
        print(f"Error in approach 1: {e}")
    
    # Approach 2: Try to find table rows and extract the first cell
    if not relays:
        try:
            # Try different selectors for table rows
            for selector in ["table tr", "tbody tr", "[role='row']", ".MuiTableRow-root", "div[class*='row']"]:
                rows = driver.find_elements(By.CSS_SELECTOR, selector)
                if rows:
                    print(f"Found {len(rows)} potential table rows with selector: {selector}")
                    
                    for row in rows:
                        try:
                            # Skip header rows
                            if row.get_attribute("role") == "columnheader" or (row.get_attribute("class") and "header" in row.get_attribute("class")):
                                continue
                            
                            # Try to get the first cell
                            cells = row.find_elements(By.CSS_SELECTOR, "td, [role='cell'], div")
                            if cells:
                                cell_text = cells[0].text.strip()
                                
                                # Skip empty text or very short text
                                if not cell_text or len(cell_text) < 5:
                                    continue
                                
                                # Skip text that doesn't look like a domain
                                if not ("." in cell_text) or any(skip in cell_text.lower() for skip in ["googleapis", "gstatic", "w3.org", "jquery", "bootstrap", "font"]):
                                    continue
                                
                                # If it looks like a relay URL but doesn't have wss://, add it
                                if not cell_text.startswith("wss://"):
                                    url = f"wss://{cell_text}"
                                else:
                                    url = cell_text
                                
                                if url not in relays:
                                    relays.append(url)
                                    print(f"Found relay from table cell: {url}")
                        except Exception as e:
                            print(f"Error processing row: {e}")
                    
                    # If we found any relays, break out of the loop
                    if relays:
                        break
        except Exception as e:
            print(f"Error in approach 2: {e}")
    
    # Approach 3: Use a more specific XPath to find the relay URLs based on the screenshot
    if not relays:
        try:
            # Based on the screenshot, the relay URLs are in the first column of a table
            # Try to find them using XPath
            relay_elements = driver.find_elements(By.XPATH, "//td[1] | //div[contains(@class, 'cell')][1] | //div[contains(@class, 'row')]/div[1]")
            
            for element in relay_elements:
                try:
                    text = element.text.strip()
                    
                    # Skip empty text or very short text
                    if not text or len(text) < 5:
                        continue
                    
                    # Skip text that doesn't look like a domain
                    if not ("." in text) or any(skip in text.lower() for skip in ["googleapis", "gstatic", "w3.org", "jquery", "bootstrap", "font"]):
                        continue
                    
                    # If it looks like a relay URL but doesn't have wss://, add it
                    if not text.startswith("wss://"):
                        url = f"wss://{text}"
                    else:
                        url = text
                    
                    if url not in relays:
                        relays.append(url)
                        print(f"Found relay from XPath: {url}")
                except:
                    continue
        except Exception as e:
            print(f"Error in approach 3: {e}")
    
    # Approach 4: If we still don't have any relays, try to extract them from the page source
    if not relays:
        try:
            # Get the page source
            page_source = driver.page_source
            
            # Use regex to find potential relay URLs
            import re
            
            # Look for text that might be a relay URL in the context of a table cell
            # This is a more specific pattern based on the HTML structure we might expect
            relay_patterns = [
                r'<td[^>]*>([\w.-]+\.[a-z]{2,}\/)</td>',  # Simple table cell with domain
                r'<div[^>]*>([\w.-]+\.[a-z]{2,}\/)</div>',  # Div with domain
                r'>([\w.-]+\.[a-z]{2,}\/)<',  # Domain between tags
                r'wss://([\w.-]+\.[a-z]{2,}\/)'  # wss:// URLs
            ]
            
            potential_relays = []
            for pattern in relay_patterns:
                matches = re.findall(pattern, page_source)
                potential_relays.extend(matches)
            
            for domain in potential_relays:
                # Skip common non-relay domains
                if any(skip in domain.lower() for skip in ["googleapis", "gstatic", "w3.org", "jquery", "bootstrap", "font"]):
                    continue
                
                # Basic validation
                if "." in domain and len(domain) > 5:
                    url = f"wss://{domain}" if not domain.startswith("wss://") else domain
                    if url not in relays:
                        relays.append(url)
                        print(f"Found relay from regex: {url}")
        except Exception as e:
            print(f"Error in approach 4: {e}")
    
    # If we still don't have any relays, print a message
    if not relays:
        print("No relays found through any extraction method. Consider manual inspection.")
    
    return relays

def go_to_next_page(driver):
    """Attempt to navigate to the next page"""
    try:
        # First, scroll to the top of the page to make sure we can see the pagination controls
        # Based on the error message, it seems the pagination controls are at the top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # Take a screenshot to see what we're working with
        driver.save_screenshot("pagination_area_top.png")
        print("Saved screenshot of pagination area to pagination_area_top.png")
        
        # Based on the error message, we need to be more careful with our element selection
        # The error indicates a click interception issue with a span element
        
        # Approach 1: Try using JavaScript to click the next page button
        # This can bypass click interception issues
        try:
            # Look for the next page button or arrow
            # From the error message, we can see it's a span with class "inline-block my-1 text-xl bg-black/10 dark:bg-white/10 py-1 px-2 rounded-sm"
            next_buttons = driver.find_elements(By.CSS_SELECTOR, "span.inline-block.my-1.text-xl")
            
            if next_buttons:
                for button in next_buttons:
                    # Check if this is the right arrow button
                    if "→" in button.text or ">" in button.text:
                        print(f"Found next button with text: {button.text}")
                        # Use JavaScript to click the button
                        driver.execute_script("arguments[0].click();", button)
                        print("Clicked next page button using JavaScript")
                        time.sleep(3)  # Allow time for page transition
                        return True
        except Exception as e:
            print(f"Error with JavaScript click approach: {e}")
        
        # Approach 2: Try to find the pagination controls more specifically
        try:
            # Look for elements that contain page numbers
            page_indicators = driver.find_elements(By.XPATH, "//*[contains(text(), 'Page') or contains(text(), 'of')]")
            
            if page_indicators:
                print(f"Found page indicator: {page_indicators[0].text}")
                
                # Try to find the parent element that contains the pagination controls
                parent = page_indicators[0]
                for _ in range(5):  # Go up to 5 levels up
                    try:
                        parent = parent.find_element(By.XPATH, "..")
                        
                        # Look for arrow buttons within this parent
                        arrows = parent.find_elements(By.XPATH, ".//*[contains(text(), '→') or contains(text(), '>')]")
                        if arrows:
                            # Use JavaScript to click the arrow
                            driver.execute_script("arguments[0].click();", arrows[0])
                            print("Clicked next page arrow within pagination parent")
                            time.sleep(3)
                            return True
                    except:
                        break
        except Exception as e:
            print(f"Error with parent navigation approach: {e}")
        
        # Approach 3: Try to extract the current page number and construct a URL for the next page
        try:
            # Look for elements that might indicate the current page
            page_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Page')]")
            
            if page_elements:
                page_text = page_elements[0].text
                print(f"Found page text: {page_text}")
                
                # Try to extract the current page number
                import re
                match = re.search(r'Page (\d+) of (\d+)', page_text)
                if match:
                    current_page = int(match.group(1))
                    total_pages = int(match.group(2))
                    print(f"Current page: {current_page}, Total pages: {total_pages}")
                    
                    if current_page < total_pages:
                        # Get the current URL
                        current_url = driver.current_url
                        
                        # Check if the URL already has a page parameter
                        if "page=" in current_url:
                            next_url = re.sub(r'page=\d+', f'page={current_page + 1}', current_url)
                        else:
                            # Add the page parameter
                            separator = "&" if "?" in current_url else "?"
                            next_url = f"{current_url}{separator}page={current_page + 1}"
                        
                        print(f"Navigating to next page URL: {next_url}")
                        driver.get(next_url)
                        time.sleep(3)
                        return True
        except Exception as e:
            print(f"Error with URL construction approach: {e}")
        
        # Approach 4: Try to find any clickable element that might be the next page button
        try:
            # Look for elements with text that suggests they're for navigation
            nav_elements = driver.find_elements(By.XPATH, 
                "//*[contains(text(), '→') or contains(text(), '>') or contains(text(), 'Next') or contains(text(), 'next')]")
            
            for elem in nav_elements:
                if elem.is_displayed() and elem.is_enabled():
                    try:
                        # Try to click it with JavaScript
                        driver.execute_script("arguments[0].click();", elem)
                        print(f"Clicked navigation element with text: {elem.text}")
                        time.sleep(3)
                        return True
                    except:
                        continue
        except Exception as e:
            print(f"Error with navigation element approach: {e}")
        
        # Approach 5: Last resort - try to manually increment the page in the URL
        try:
            current_url = driver.current_url
            # Check if we can identify a page parameter in the URL
            if "page=" in current_url:
                # Extract the current page number
                match = re.search(r'page=(\d+)', current_url)
                if match:
                    current_page = int(match.group(1))
                    next_url = re.sub(r'page=\d+', f'page={current_page + 1}', current_url)
                    print(f"Navigating to next page URL: {next_url}")
                    driver.get(next_url)
                    time.sleep(3)
                    return True
            else:
                # Try adding a page parameter
                separator = "&" if "?" in current_url else "?"
                next_url = f"{current_url}{separator}page=2"  # Assume we're on page 1
                print(f"Navigating to next page URL: {next_url}")
                driver.get(next_url)
                time.sleep(3)
                return True
        except Exception as e:
            print(f"Error with URL manipulation approach: {e}")
        
        print("Could not find a way to navigate to the next page")
        return False
    
    except Exception as e:
        print(f"Error navigating to next page: {e}")
        return False

def scrape_relays(url="https://next.nostr.watch/relays", max_pages=None, page_load_timeout=60):
    """
    Scrape relay information from the specified URL
    
    Args:
        url: The URL to scrape
        max_pages: Maximum number of pages to scrape (None for all pages)
        
    Returns:
        List of relay URLs
    """
    all_relays = []
    
    # Setup browser
    options = setup_browser_options()
    
    try:
        driver = webdriver.Chrome(options=options)
        # Set page load timeout
        driver.set_page_load_timeout(page_load_timeout)
        print(f"Navigating to {url}")
        driver.get(url)
        
        # Give the page some time to start loading
        time.sleep(5)
        
        # Process pages
        page_num = 1
        max_attempts = 10  # Maximum number of attempts to navigate to new pages
        previous_page_relays = set()  # Keep track of relays on the previous page
        duplicate_page_count = 0  # Count how many times we've seen the same page
        
        # If max_pages is not specified, set a reasonable default to avoid infinite loops
        if max_pages is None:
            max_pages = 20  # Reasonable default
        
        while page_num <= max_pages:
            print(f"\nProcessing page {page_num}...")
            
            # Wait for content to load
            if not wait_for_content(driver):
                print("Failed to load content, taking a screenshot for debugging")
                driver.save_screenshot(f"page_{page_num}_error.png")
                break
            
            # Extract relay URLs from current page
            page_relays = extract_relays_from_page(driver)
            print(f"Found {len(page_relays)} relays on page {page_num}")
            
            # Check if we're seeing the same relays again
            current_page_relays = set(page_relays)
            if current_page_relays and current_page_relays == previous_page_relays:
                duplicate_page_count += 1
                print(f"Warning: Same relays found as previous page (duplicate count: {duplicate_page_count})")
                
                if duplicate_page_count >= 3:
                    print("Detected page cycling, stopping scraping")
                    break
            else:
                duplicate_page_count = 0  # Reset counter if we see new relays
                previous_page_relays = current_page_relays
            
            # Add the relays to our collection
            all_relays.extend(page_relays)
            
            # Try to go to next page, break if no more pages
            if not go_to_next_page(driver):
                print("No more pages")
                break
            
            # Take a screenshot after navigation attempt
            driver.save_screenshot(f"after_navigation_page_{page_num}.png")
            
            # Verify that we've actually navigated to a new page
            # Wait a moment for the page to load
            time.sleep(5)
            
            page_num += 1
        
        # Remove duplicates while preserving order
        unique_relays = []
        seen = set()
        for relay in all_relays:
            if relay not in seen:
                seen.add(relay)
                unique_relays.append(relay)
        
        print(f"\nScraped {len(unique_relays)} unique relays from {page_num} pages")
        return unique_relays
    
    except WebDriverException as e:
        print(f"WebDriver error: {e}")
        print("Make sure you have Chrome and ChromeDriver installed and compatible")
        return []
    
    except Exception as e:
        print(f"Error during scraping: {e}")
        return []
    
    finally:
        try:
            driver.quit()
        except:
            pass

def save_relays_to_file(relays, filename):
    """Save relay URLs to a file, one per line"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, "w") as f:
        for relay in relays:
            f.write(f"{relay}\n")
    
    print(f"Saved {len(relays)} relays to {filename}")

def main():
    """Main function to run the scraper"""
    parser = argparse.ArgumentParser(description="Scrape relay information from next.nostr.watch/relays")
    parser.add_argument("--url", default="https://next.nostr.watch/relays", help="URL to scrape")
    parser.add_argument("--max-pages", type=int, default=5, help="Maximum number of pages to scrape (default: 5)")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--timeout", type=int, default=60, help="Page load timeout in seconds")
    parser.add_argument("--filter", help="Filter relays by domain (e.g., 'nostr1.com' to only include relays with that domain)")
    args = parser.parse_args()
    
    # Scrape relays
    relays = scrape_relays(args.url, args.max_pages, args.timeout)
    
    # Apply filter if specified
    if args.filter and relays:
        filtered_relays = [r for r in relays if args.filter in r]
        print(f"Filtered from {len(relays)} to {len(filtered_relays)} relays containing '{args.filter}'")
        relays = filtered_relays
    
    if not relays:
        print("No relays found")
        return
    
    # Generate output filename if not provided
    if not args.output:
        timestamp = datetime.now().strftime("%d%b%Y").upper()
        args.output = f"utility/scanner/scraped_relays_as_of_{timestamp}.txt"
    
    # Save to file
    save_relays_to_file(relays, args.output)

if __name__ == "__main__":
    main()
