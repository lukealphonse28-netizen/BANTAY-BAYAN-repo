from bs4 import BeautifulSoup
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from pathlib import Path
from datetime import datetime
import hashlib
import json
import requests
import time
import schedule
import re

# --- Configuration Constants ---
HEADLESS = True  # Set to False to show the browser
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbxFdvSPPks_xW0sUsG8aXNMgze-yiRcPm7ql_MMg1GTEGu0-484bTftgSI6ei95xGIu/exec"
SAVED_DATA_PATH = r"C:\Users\Luke\OneDrive\Documents\Scraped Data"

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    if HEADLESS:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)

def web_ScraperLinks():
    servant_links = []
    driver = create_driver()
    try:
        driver.get("https://quezoncity.gov.ph/")
        menu_button = driver.find_element(By.TAG_NAME, "button")
        menu_button.click()
        dropdown_options = driver.find_elements(By.TAG_NAME, "a")
        for option in dropdown_options:
            href = option.get_attribute("href")
            if href and "public-servants" in href:
                servant_links.append(href)
    finally:
        driver.quit()
    return list(set(servant_links))

def clean_text_formatting(raw_text):
    lines = raw_text.splitlines()
    cleaned_lines = []
    ignore_phrases = [
        "Open toolbar", "Accessibility Tools", "Grayscale", "Negative Contrast", 
        "Links Underline", "Readable Font", "Reset", "Accessibility Statement", 
        "Skip to main content", "Privacy Policy", "Contact Us", "QC:122 Report an issue",
        "Select any text and click on the icon to listen!", "GSpeech", "Skip to content", "Play"
    ]
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(phrase.lower() in stripped.lower() for phrase in ignore_phrases):
            continue
        cleaned_lines.append(stripped)
        
    return "\n".join(cleaned_lines)

def web_scraperInfo(servant_links):
    open_folder = Path(SAVED_DATA_PATH)
    open_folder.mkdir(parents=True, exist_ok=True)
    
    master_content = []

    print("Scraping individual politician profile pages, dropdowns, and redirects...")
    for link in servant_links:
        driver = create_driver()
        try:
            driver.get(link)
            
            # 1. View Full Profile Redirect Logic
            try:
                full_profile_btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "View Full Profile"))
                )
                full_profile_btn.click()
                time.sleep(2)
            except Exception:
                pass

            # 2. Year Dropdown Accordion Expansion Logic (Mayor Joy & Councilors)
            try:
                year_buttons = driver.find_elements(By.XPATH, "//*[self::button or self::div or self::span][contains(text(), '2026') or contains(text(), '2025') or contains(text(), '2024') or contains(text(), '2023') or contains(text(), '2022') or contains(text(), '2021') or contains(text(), '2020') or contains(text(), '2019')]")
                actions = ActionChains(driver)
                for btn in year_buttons:
                    try:
                        if btn.is_displayed():
                            actions.move_to_element(btn).click().perform()
                            time.sleep(0.3)
                    except Exception:
                        continue
            except Exception:
                pass

            body_elem = driver.find_element(By.TAG_NAME, "body")
            raw_text = body_elem.text
            formatted_text = clean_text_formatting(raw_text)
            
            if len(formatted_text.strip()) > 50:
                master_content.append(f"\n\n--- START POLITICIAN PROFILE ---\n{formatted_text}\n--- END POLITICIAN PROFILE ---\n")
                
        except Exception as e:
            print(f"Error scraping link {link}: {e}")
        finally:
            driver.quit()

    master_file_path = open_folder / "all_politicians_master.txt"
    full_master_text = "".join(master_content)
    
    new_hash = hashlib.md5(full_master_text.encode("utf-8")).hexdigest()
    file_exists = master_file_path.exists()
    is_updated = True

    if file_exists:
        with open(master_file_path, "r", encoding="utf-8") as f:
            old_content = f.read()
            old_hash = hashlib.md5(old_content.encode("utf-8")).hexdigest()
        if new_hash == old_hash:
            is_updated = False

    if is_updated:
        with open(master_file_path, "w", encoding="utf-8") as f:
            f.write(full_master_text)
        print("[UPDATE DETECTED] Master file updated with full web data.")
        split_master_into_individual_files(master_file_path, open_folder)
        return True
    else:
        print("[NO CHANGE] Website data is identical to the master file cache.")
        return False

def split_master_into_individual_files(master_path, folder_path):
    print("Arranging and splitting master file into individual politician files...")
    with open(master_path, "r", encoding="utf-8") as f:
        master_text = f.read()

    profiles = master_text.split("--- START POLITICIAN PROFILE ---")
    
    for index, profile in enumerate(profiles):
        if not profile.strip():
            continue
            
        profile_clean = profile.split("--- END POLITICIAN PROFILE ---")[0].strip()
        lines = [line.strip() for line in profile_clean.splitlines() if line.strip()]
        
        # Smart Name Extractor directly from top lines
        politician_name = f"servant_{index}"
        for line in lines[:10]:
            if any(title in line.lower() for title in ["hon.", "mayor", "vice mayor", "councilor"]):
                clean_line = re.sub(r'(- Quezon City Government|Home.*|».*)', '', line, flags=re.IGNORECASE).strip()
                if 3 < len(clean_line) < 60:
                    politician_name = clean_line
                    break

        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', politician_name).lower()
        individual_file_path = folder_path / f"politician_{safe_name}.txt"

        with open(individual_file_path, "w", encoding="utf-8") as ind_file:
            ind_file.write(profile_clean)
            
    print("Successfully arranged and generated individual politician text files!")

def parse_data_with_python_regex(raw_text):
    """Direct Python parsing fallback to extract Name, Role, and Date from text."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # 1. Extract Name
    name = ""
    for line in lines[:10]:
        if any(t in line.lower() for t in ["hon.", "mayor", "vice mayor", "councilor"]):
            clean = re.sub(r'(- Quezon City Government|Home.*|».*)', '', line, flags=re.IGNORECASE).strip()
            if 3 < len(clean) < 60:
                name = clean
                break
    if not name and len(lines) > 0:
        name = lines[0]

    # 2. Extract Role
    role = "City Councilor"
    text_lower = raw_text.lower()
    if "city mayor" in text_lower or "11th elected mayor" in text_lower:
        role = "City Mayor"
    elif "vice mayor" in text_lower or "presiding officer" in text_lower:
        role = "City Vice Mayor"
    elif "councilor" in text_lower:
        # Catch District info if present (e.g. Councilor, District 1)
        match = re.search(r'councilor,\s*district\s*\d', text_lower)
        if match:
            role = match.group(0).title()

    # 3. Extract Date (Search for dates like "10 October 2026" or "2026-10-10")
    date_val = datetime.now().strftime("%Y-%m-%d") # Default to current date
    date_match = re.search(r'(\d{1,2}\s+[A-Za-z]+\s+20\d{2})|(20\d{2}-\d{2}-\d{2})', raw_text)
    if date_match:
        date_val = date_match.group(0)

    # 4. Extract Summary (Grab first non-title paragraph)
    summary = "Public servant serving in the Quezon City Local Government Unit."
    for line in lines[3:15]:
        if len(line) > 60 and not line.startswith("http"):
            summary = line
            break

    return {
        "date": date_val,
        "name": name if name else "Public Servant",
        "role": role,
        "hierarchy_level": "Local",
        "region_lgu": "Quezon City",
        "rating": 6,
        "summary": summary
    }

def analyze_and_sync_files():
    client = OpenAI(
        base_url="http://localhost:11434/v1/",
        api_key="ollama"
    )

    open_folder = Path(SAVED_DATA_PATH)
    
    for file_path in open_folder.glob("politician_*.txt"):
        if file_path.name == "all_politicians_master.txt":
            continue # Skip the master file itself

        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        print(f"Analyzing {file_path.name}...")

        # Python Regex Pre-Parsing (Guarantees data availability)
        python_extracted = parse_data_with_python_regex(raw_text)

        system_prompt = (
            "You are a data-structuring assistant for Philippine local government portals. "
            "Extract politician information from the raw text and output a valid JSON object "
            "with a single key 'records' containing an array with a single object. "
            "Each object must have these exact keys: "
            "'date' (YYYY-MM-DD), 'name', 'role', 'hierarchy_level' "
            "(strictly choose: 'National', 'Congressional', 'Provincial', or 'Local'), "
            "'region_lgu', 'rating' (an integer from 1 to 10 evaluating their performance), "
            "and 'summary' (a concise 2-sentence summary of accomplishments)."
        )

        records = []
        try:
            response = client.chat.completions.create(
                model="llama3.2:latest",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Raw scraped data:\n\n{raw_text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            content = response.choices[0].message.content.strip()
            content = content.removeprefix("```json").removeprefix("```")
            content = content.removesuffix("```").strip()

            if content:
                parsed_data = json.loads(content)
                extracted = parsed_data.get("records", [])
                if isinstance(extracted, list):
                    records = [item for item in extracted if isinstance(item, dict)]

        except Exception:
            records = []

        # Combine Ollama JSON with Python Regex Parsing to ensure NO UNKNOWNS
        if records:
            item = records[0]
            final_name = item.get("name") if item.get("name") and item.get("name").lower() not in ["unknown", "n/a", ""] else python_extracted["name"]
            final_role = item.get("role") if item.get("role") and item.get("role").lower() not in ["unknown", "n/a", ""] else python_extracted["role"]
            final_date = item.get("date") if item.get("date") and item.get("date").lower() not in ["unknown", "n/a", ""] else python_extracted["date"]
            final_summary = item.get("summary") if item.get("summary") and item.get("summary").lower() not in ["unknown", "n/a", ""] else python_extracted["summary"]
            final_rating = item.get("rating", 6)
        else:
            final_name = python_extracted["name"]
            final_role = python_extracted["role"]
            final_date = python_extracted["date"]
            final_summary = python_extracted["summary"]
            final_rating = python_extracted["rating"]

        formatted_rows = [[
            str(final_date),
            str(final_name),
            str(final_role),
            "Local",
            "Quezon City",
            int(final_rating),
            str(final_summary)
        ]]

        try:
            payload = {"rows": formatted_rows}
            print(f"Syncing [{final_name} | {final_role}] to Google Sheets...")
            
            res = requests.post(WEB_APP_URL, json=payload, timeout=30)
            print("Google Sheets Response:", res.json())
            
        except requests.RequestException as net_err:
            print(f"Network error syncing {file_path.name} to Google Sheets: {net_err}")
        except json.JSONDecodeError:
            print(f"Apps Script did not return valid JSON for {file_path.name}. Check your Web App permissions!")

def run_pipeline():
    print(f"\n--- Scheduled Job Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    print("1. Scraping links...")
    servant_links = web_ScraperLinks()
    
    if not servant_links:
        print("No links found. Skipping this run.")
        return

    print("2. Scraping info into master file and checking updates...")
    has_updates = web_scraperInfo(servant_links)  
    
    if has_updates:
        print("3. Running analysis and syncing real data to Google Sheets...")
        analyze_and_sync_files()
    else:
        print("3. Skipping sync because no website updates were found.")
    
    print("--- Job Finished ---")

if __name__ == "__main__":
    schedule.every(6).hours.do(run_pipeline)
    print("LGU Scraper Scheduler is active. Press Ctrl+C to stop.")
    
    run_pipeline()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOPPED] Scheduler stopped safely by user.")
        schedule.clear()