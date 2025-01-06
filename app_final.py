import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import time
import re
import unicodedata

API_URL = "https://api.data.gov.in/resource/9115b89c-7a80-4f54-9b06-21086e0f0bd7"
API_KEY = "579b464db66ec23bdd00000128491f22b83a4d0d4826b4eb59f2eeef"

COUNTRY_STATES_URL = "https://countriesnow.space/api/v0.1/countries/states"
STATE_CITIES_URL = "https://countriesnow.space/api/v0.1/countries/state/cities"

def get_states(country):
    response = requests.post(COUNTRY_STATES_URL, json={"country": country})
    if response.status_code == 200:
        states = response.json().get("data", {}).get("states", [])
        if country == "Sri Lanka":
            states = [state for state in states if "District" not in state['name']]
            states = [state for state in states if "district" not in state['name']]
        return states
    else:
        st.error("Failed to fetch states")
        return []

def get_cities(country, state):
    response = requests.post(STATE_CITIES_URL, json={"country": country, "state": state})
    if response.status_code == 200:
        cities = response.json().get("data", [])
        return cities if cities else ["N/A"]  # Return ["N/A"] if no cities are found
    else:
        st.error("Failed to fetch cities")
        return ["N/A"]

def get_district_data(district_name):
    district_name = ''.join(c for c in unicodedata.normalize('NFD', district_name) if not unicodedata.combining(c)).upper()
    st.write(district_name)
    if district_name == 'BENGALURU':
        district_name = 'BANGALORE'
    if district_name == 'MYSORE':
        district_name = "Mysuru"
    if district_name == 'KANPUR':
        district_name = 'KANPUR NAGAR'
    params = {
        "api-key": API_KEY,
        "format": "json",
        "filters[districtname]": district_name,
        "limit": 100,
    }
    response = requests.get(API_URL, params=params)
    if response.status_code == 200:
        return response.json().get("records", [])
    else:
        st.error("Failed to fetch district data")
        return []

def scrape_places(search_queries, subc):
    results = []
    seen_names = set()
    total_queries = len(search_queries)
    
    progress_bar = st.progress(0)   
    status_text = st.empty()         

    for index, search_query in enumerate(search_queries):
        
        if search_query in seen_names:
            status_text.text(f"Skipping already processed area: {search_query} ({index + 1}/{total_queries})")
            continue

       
        status_text.text(f"Processing area: {search_query} ({index + 1}/{total_queries})")
        
       
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

       
        url = f"https://www.google.com/maps/search/{search_query}+dealers in+{subc}/"
        driver.get(url)
        driver.implicitly_wait(1)

       
        def scroll_panel_with_page_down(driver, panel_xpath, presses, pause_time):
            panel_element = driver.find_element(By.XPATH, panel_xpath)
            actions = ActionChains(driver)
            actions.move_to_element(panel_element).click().perform()
            for _ in range(presses):        
                actions.send_keys(Keys.PAGE_DOWN).perform()
                time.sleep(pause_time)

        panel_xpath = "//*[@id='QA0Szd']/div/div/div[1]/div[2]/div"
        scroll_panel_with_page_down(driver, panel_xpath, presses=100, pause_time=0)

        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        
        def get_text_or_na(element):
            return element.text if element else 'N/A'

        titles = soup.find_all(class_="hfpxzc")

        for i, title in enumerate(titles):
            title_text = title.get('aria-label') if title else 'N/A'
            parent = title.find_parent('div').find_parent('div')

            if title_text in seen_names:
                continue

            
            rating_element = parent.find(class_='MW4etd')
            review_element = parent.find(class_='UY7F9')
            service_element = parent.find(class_='Ahnjwc')
            description_element = parent.find_all(class_='W4Efsd')[1]  # Select the second 'W4Efsd' div

            allinfo_element = parent.find(class_='lI9IFe')
            phone_element = parent.find(class_='UsdlK')
            website_element = parent.find(class_='lcr4fd S9kvJb')

            rating_text = get_text_or_na(rating_element) + "/5" if rating_element else 'N/A'
            review_count_text = get_text_or_na(review_element)
            review_count = int(review_count_text.strip('()').replace(',', '')) if review_count_text != 'N/A' else 'N/A'
            service_text = get_text_or_na(service_element)
            description_text = get_text_or_na(description_element.find_all('span')[1])
            allinfo_text = get_text_or_na(allinfo_element)
            phone_text = get_text_or_na(phone_element)
            website_text = website_element.get('href') if website_element else 'N/A'

           
            if 'Open' in allinfo_text:
                address_pattern = re.compile(r'\)\s*(.*?)\s*Open', re.IGNORECASE)
            elif 'No reviews' in allinfo_text:
                if 'Temporarily closed' in allinfo_text:
                    address_pattern = re.compile(r'No reviews\s*(.*?)\s*Temporarily closed', re.IGNORECASE)
                else:
                    address_pattern = re.compile(r'No reviews\s*(.*?)\s*Directions', re.IGNORECASE)
            else:
                address_pattern = re.compile(r'No reviews\s*(.*?)(?:\s*Directions|$)', re.IGNORECASE)

            address_match = address_pattern.search(allinfo_text)
            address_text = address_match.group(1).strip() if address_match else 'N/A'

            results.append({
                'Name': title_text,
                'Rating': rating_text,
                'Reviews': review_count,
                'Service options': service_text,
                'Description': description_text,
                'All-info': allinfo_text,
                'Phone Number': phone_text,
                'Address': address_text,
                'Website': website_text
            })

            seen_names.add(title_text)  

        
        driver.quit()
        
        
        progress_bar.progress((index + 1) / total_queries)
        eta = (total_queries - index - 1) * 5  
        status_text.text(f"Processing area: {search_query} ({index + 1}/{total_queries})\nEstimated time remaining: {eta} seconds")
        
    return results


def main():
    st.title("Matex Search Tool")

    country = st.selectbox("Select a country", ["India", "United Arab Emirates", "Egypt", "Saudi Arabia", "Sri Lanka", "Philippines"])  
    if country:
        states = get_states(country)
        state = st.selectbox("Select a state", [state['name'] for state in states])

        if state:
            cities = get_cities(country, state)
            city = st.selectbox("Select a city", cities + ["N/A"])

            sub_c = st.text_input("Enter a sub-category (e.g., scrap): ")

            if st.button("Fetch Data"):
                if city == "N/A":
                    search_queries = [f"{state}, {country}"]
                else:
                    district_data = get_district_data(city)
                    if district_data:
                        st.write(f"Found {len(district_data)} nearby places in district '{city}'.")
                        search_queries = [record['officename___bo_so_ho_'] for record in district_data]
                    else:
                        st.write("No district data found. Using city name as search query.")
                        search_queries = [f"{city}, {state}, {country}"]

                if sub_c:
                    search_queries = [f"{query} {sub_c}" for query in search_queries]

                with st.spinner("Scraping data..."):
                    combined_results = scrape_places(search_queries, sub_c)

                    if combined_results:
                        st.write(f"Found {len(combined_results)} places.")
                        df = pd.DataFrame(combined_results)
                        st.dataframe(df)

                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="Download data as CSV and pick new city",
                            data=csv,
                            file_name=f'{state}_scrap_dealers.csv',
                            mime='text/csv',
                        )
                    else:
                        st.write("No data found during scraping.")
            else:
                st.error("Please click on the 'Fetch Data' button to start the process.")
        else:
            st.error("Please select a state to continue.")
    else:
        st.error("Please select a country to continue.")

if __name__ == "__main__":
    main()
