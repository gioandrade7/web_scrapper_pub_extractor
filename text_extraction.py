from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

chromeOptions = Options()

# Option to keep the browser window open after script execution
chromeOptions.add_experimental_option("detach", True)
# Uncomment this line to run in headless mode (Chrome browser invisible)
chromeOptions.add_argument("--headless=new")

driver = webdriver.Chrome(options=chromeOptions)

# Function to extract text from a URL
def text_extraction(driver, url):
    driver.get(url)  # Navigate to the URL
    
    # Locate the element containing the text
    texto = driver.find_element(By.CLASS_NAME, "texto-dou")
    
    # Find all paragraph tags within the text container
    paragrafos = texto.find_elements(By.TAG_NAME, 'p')
    
    # Extract the text from each paragraph and join them into a single string
    extracted_text = ' '.join([p.text for p in paragrafos])
    
    return extracted_text