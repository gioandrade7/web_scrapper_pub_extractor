# Necessary imports
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from text_extraction import text_extraction
import ast

# Setup Chrome options
chromeOptions = Options()
# Option to keep the browser window open after script execution
chromeOptions.add_experimental_option("detach", True)
# Uncomment this line to run in headless mode (Chrome browser invisible)
chromeOptions.add_argument("--headless=new")

# Initialize Chrome driver
driver = webdriver.Chrome(options=chromeOptions)

url = "..." # URL of the DOU section for a specific date
# Access the webpage
driver.get(url)

# Find and click the button using its ID

button = driver.find_element(By.ID, "viewMenuOptionTree")
driver.execute_script("arguments[0].click();", button)

# Verify if the tree element is displayed
if (driver.find_element(By.XPATH, "/html/body/div[1]/div[1]/main/div[2]/div/div[2]/div/div/div/div[4]/section/div/div[2]/div/div[4]/div[2]/ul").is_displayed()):
    print("Tree element is displayed")
    tree = driver.find_element(By.XPATH, "/html/body/div[1]/div[1]/main/div[2]/div/div[2]/div/div/div/div[4]/section/div/div[2]/div/div[4]/div[2]/ul")

# Extract publication links
driver.implicitly_wait(10)
files = tree.find_elements(By.CLASS_NAME, "file")
pubs = []
print(f'Total publications: {len(files)}')
count = 0
for file in files:
    pub_link = file.find_element(By.TAG_NAME, 'a').get_attribute('href')
    print(f'Pub {count} extraída...')
    count += 1
    pubs.append(text_extraction(pub_link))


path_to_save = '' # Directory to save the extracted publications
pubs_extracted = open(path_to_save, "a")

pubs_extracted.write(str(pubs))


