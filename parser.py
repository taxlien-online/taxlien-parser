import os
import argparse
from bs4 import BeautifulSoup # type: ignore
from datetime import datetime
from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.common.keys import Keys # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.webdriver.chrome.service import Service # type: ignore
from selenium.webdriver.chrome.options import Options # type: ignore

from config import PATH_CHROMEDRIVER, PATH_INPUT, PATH_OUTPUT

chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")


service = Service(PATH_CHROMEDRIVER)
driver = webdriver.Chrome(service=service, options=chrome_options)

def extract_parcel_info(html_file):
		try:
				with open(html_file, 'r', encoding='utf-8') as file:
						soup = BeautifulSoup(file, 'html.parser')
						
						form = soup.find('form', {'name': 'PhotoForm'})
						
						if form:
								parcel_id = form.find('input', {'name': 'Photo_PIN'})['value']
								owner = form.find('input', {'name': 'strOwner'})['value'].replace('<br>', '; ').replace("'", "")
								site_address = form.find('input', {'name': 'strSiteAddress'})['value'].replace("'", "")
								legal_description = form.find('input', {'name': 'strLegal'})['value'].replace('  ', ' ').replace("'", "").replace('(', '').replace(')', '')
								print(f"Извлечение данных - {parcel_id}")
						else:
								parcel_id = owner = site_address = legal_description = 'N/A'

						pin = 'R' + parcel_id[9:18]
						
						sales_history_table = soup.find(string=lambda text: text and 'Sales History' in text)

						sales_history = []
						if sales_history_table:
								table = sales_history_table.find_next('table')
								if table:
										rows = table.find_all('tr')[1:]
										for row in rows:
												cells = row.find_all('td')
												if len(cells) >= 5:
														
														price = cells[1].text.strip().replace('$', '').replace(',', '').replace('(', '').replace(')', '')
														
														sale_date = cells[0].text.strip()
														sale_date = convert_date_format(sale_date)
														sale = {
																'parcel_id': parcel_id,
																'sale_date': sale_date,
																'price': price,
																'book_page': cells[2].text.strip(),
																'deed': cells[3].text.strip(),
																'vi': cells[4].text.strip()
														}
														sales_history.append(sale)
						
						tax_payment_history = fetch_tax_payment_history(pin, parcel_id)
						return {
								'parcel_id': parcel_id,
								'owner': owner,
								'site_address': site_address,
								'legal_description': legal_description,
								'sales_history': sales_history,
								'property_tax_account': pin,
								'tax_payment_history': tax_payment_history
						}
		except Exception as e:
				print(f"Ошибка при обработке {html_file}: {e}")
				return None

def open_driver():
		driver = webdriver.Chrome(service=service, options=chrome_options)
		return driver

def fetch_tax_payment_history(pin, parcel_id):
		try:
				result = 0
				url = f"https://columbia.floridatax.us/PropertyDetail?p={pin}"
				driver = open_driver()
				
				driver.get(url)

				wait = WebDriverWait(driver, 30)

				try:
						captcha_element_present = driver.find_elements(By.ID, 'MainContent_txtNumber3')
						
						if captcha_element_present:
								print(f"Капча обнаружена для PIN {pin}, начинаем решение.")
								
								captcha_element = wait.until(EC.element_to_be_clickable((By.ID, 'MainContent_txtNumber3')))
								captcha_element.click()

								number1 = int(driver.find_element(By.ID, 'MainContent_lblNumber1').text)
								number2 = int(driver.find_element(By.ID, 'MainContent_lblNumber2').text)
								result = number1 + number2

								captcha_input = driver.find_element(By.ID, 'MainContent_txtNumber3')
								captcha_input.send_keys(str(result))

								human_checkbox = driver.find_element(By.ID, 'MainContent_chkHuman')
								human_checkbox.click()

								submit_button = driver.find_element(By.ID, 'MainContent_btnHuman')
								submit_button.click()

						else:
								print(f"Капча не найдена для PIN {pin}, переходим к парсингу.")

				except Exception as e:
						print(f"Ошибка при вводе капчи или её проверке для PIN {pin}: {e}")

				try:
						soup = BeautifulSoup(driver.page_source, 'html.parser')
						payment_history_section = soup.find('table', {'id': 'MainContent_PropertyContainer_tpTransactionHistory_TransactionHistoryGrid'})
						tax_payment_history = []

						if payment_history_section:
								rows = payment_history_section.find_all('tr')
								print(f"Извлечение истории налогов для PIN {pin}: {len(rows)}")
								for row in rows[1:]:
										cells = row.find_all('td')
										if len(cells) >= 5:
												payment = {
														'parcel_id': parcel_id,
														'tax_year': cells[1].text.strip(),
														'payment_date': convert_date_format(cells[5].text.strip()),
														'receipt_number': cells[3].text.strip(),
														'paid_by': cells[4].text.strip().replace(" &'", "'").replace(" & ", " and ").replace("'", ""),
														'paid_amount': cells[6].text.strip().replace('$', '').replace(',', '')
												}
												tax_payment_history.append(payment)
						else:
								print(f"Извлечение истории налогов для PIN {pin}: Нет таблицы истории налогов")

						driver.quit()
						return tax_payment_history

				except Exception as e:
						print(f"Ошибка при извлечении истории налогов для PIN {pin}: {e}")
						driver.quit()
						return []

		except Exception as e:
				print(f"Ошибка при обработке истории налогов для PIN {pin}: {e}")
				driver.quit()
				return []



def convert_date_format(date_str):
		try:
				date_obj = datetime.strptime(date_str, '%m/%d/%Y')
				return date_obj.strftime('%Y-%m-%d')
		except ValueError:
				print(f"Неверный формат даты: {date_str}")
				return date_str

def process_folder_sequential(folder_path, output_folder, start_file=None):
		html_files = [os.path.join(folder_path, filename) for filename in os.listdir(folder_path) if filename.endswith('.html')]

		# Найти индекс стартового файла
		start_index = 0
		if start_file:
				try:
						start_index = html_files.index(os.path.join(folder_path, start_file))
				except ValueError:
						print(f"Файл {start_file} не найден в папке. Начинаем с первого файла.")

		for pos, html_file in enumerate(html_files[start_index:], start=start_index+1):
				parcel_info = extract_parcel_info(html_file)
				if parcel_info:
						is_last_file = pos == len(html_files)
						parcels_sql = generate_parcels_sql([{
								'parcel_id': parcel_info['parcel_id'],
								'owner': parcel_info['owner'],
								'site_address': parcel_info['site_address'],
								'legal_description': parcel_info['legal_description'],
								'property_tax_account': parcel_info['property_tax_account']
						}], is_last_file)
						sales_sql = generate_sales_sql(parcel_info['sales_history'], is_last_file)
						tax_payment_sql = generate_tax_payment_sql(parcel_info['tax_payment_history'], is_last_file)

						append_sql_to_file(parcels_sql, output_folder, 'parcels.sql')
						append_sql_to_file(sales_sql, output_folder, 'sales_history.sql')
						append_sql_to_file(tax_payment_sql, output_folder, 'tax_payment_history.sql')

def generate_parcels_sql(data, last):
		sql_query = ""
		values = []
		for parcel in data:
				value = f"('{parcel['parcel_id']}', '{parcel['owner']}', '{parcel['site_address']}', '{parcel['legal_description']}', '{parcel['property_tax_account']}')"
				values.append(value)
		sql_query += ",\n".join(values)
		if last:
			sql_query += ";\n"
		else:
			sql_query += ",\n"
		return sql_query

def generate_sales_sql(sales_data, last):
		sql_query = ""
		values = []
		for sale in sales_data:
				value = f"('{sale['parcel_id']}', '{sale['sale_date']}', '{sale['price']}', '{sale['book_page']}', '{sale['deed']}', '{sale['vi']}')"
				values.append(value)
		sql_query += ",\n".join(values)
		if last:
			sql_query += ";\n"
		else:
			sql_query += ",\n"
		return sql_query

def generate_tax_payment_sql(tax_payment_data, last):
		sql_query = ""
		values = []
		for payment in tax_payment_data:
				value = f"('{payment['parcel_id']}', '{payment['tax_year']}', '{payment['payment_date']}', '{payment['receipt_number']}', '{payment['paid_by']}', '{payment['paid_amount']}')"
				values.append(value)
		sql_query += ",\n".join(values)
		if last:
			sql_query += ";\n"
		else:
			sql_query += ",\n"
		return sql_query

def append_sql_to_file(sql_query, output_folder, filename):
		file_path = os.path.join(output_folder, filename)
		with open(file_path, 'a', encoding='utf-8') as f:
				f.write(sql_query)

if __name__ == "__main__":
		parser = argparse.ArgumentParser(description="Парсинг HTML файлов и генерация SQL.")
		parser.add_argument("--start_file", type=str, help="Имя файла, с которого начать обработку.")
		
		args = parser.parse_args()

		folder_path = PATH_INPUT
		output_folder = PATH_OUTPUT

		append_sql_to_file("INSERT INTO taxlien.parcels (parcel_id,owner,site_address,legal_description,property_tax_account) VALUES\n", output_folder, 'parcels.sql')
		append_sql_to_file("INSERT INTO taxlien.sales_history (parcel_id,sale_date,price,book_page,deed,vi) VALUES\n", output_folder, 'sales_history.sql')
		append_sql_to_file("INSERT INTO taxlien.tax_payment_history (parcel_id,tax_year,payment_date,receipt_number,paid_by,paid_amount) VALUES\n", output_folder, 'tax_payment_history.sql')

		process_folder_sequential(folder_path, output_folder, start_file=args.start_file)