import requests
from bs4 import BeautifulSoup
import urllib3
import schedule
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# Configuración inicial
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def obtener_datos_bcb():
    """Extrae el Dólar Referencial del Banco Central de Bolivia."""
    url = "https://www.bcb.gob.bo/"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        cards = soup.find_all('article', class_='bcb-kpi2-card')
        for card in cards:
            titulo = card.find('p', class_='bcb-kpi2-name')
            if titulo and "Valor referencial" in titulo.text:
                vals = card.find_all('div', class_='bcb-val')
                compra = vals[0].get_text(strip=True)
                venta = vals[1].get_text(strip=True)
                return f"BCB Referencial  | Compra: {compra} | Venta: {venta}"
    except Exception as e:
        return f"Error en BCB: {e}"
    return "BCB: No se encontró el dato."

def obtener_datos_bisa():
    """Extrae los valores de USDTs del Banco Bisa."""
    url = "https://www.bisa.com/home"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        spans = soup.find_all('span')
        compra, venta = "N/A", "N/A"
        for s in spans:
            texto = s.get_text(strip=True)
            if "USDTs Compra" in texto:
                compra = texto.replace("USDTs Compra", "").strip()
            elif "USDTs Venta" in texto:
                venta = texto.replace("USDTs Venta", "").strip()
        return f"BISA USDTs       | Compra: {compra} | Venta: {venta}"
    except Exception as e:
        return f"Error en BISA: {e}"

def obtener_datos_bcp():
    """Extrae USDT Venta del BCP manejando pop-ups y carga dinámica."""
    url = "https://www.bcp.com.bo/"
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--window-size=1920,1080") # Simular pantalla grande
    chrome_options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        wait = WebDriverWait(driver, 20)

        # 1. Intentar cerrar el pop-up si aparece
        try:
            # Buscamos el botón de cerrar (la 'x')
            btn_cerrar = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "cerrarBtn1")))
            btn_cerrar.click()
            time.sleep(1) # Pausa breve tras cerrar
        except:
            # Si no aparece el pop-up, continuamos
            pass

        # 2. Esperar a que la marquesina tenga contenido real
        # A veces el div existe pero está vacío mientras carga el script
        wait.until(lambda d: "USDT Venta" in d.find_element(By.CLASS_NAME, "marquee-content").text)

        # 3. Extraer el contenido usando JavaScript (más robusto)
        contenido = driver.execute_script("return document.querySelector('.marquee-content').innerText;")
        
        # Procesar el texto obtenido
        # El texto suele venir como: "Dólar Compra: 6.85 | Dólar Venta: 6.97 | USDT Venta: 9.45"
        partes = contenido.split('|')
        for parte in partes:
            if "USDT Venta" in parte:
                valor = parte.replace("USDT Venta:", "").strip()
                return f"BCP USDT         | Venta: {valor}"
        
        return "BCP: Texto USDT no encontrado en el bloque."

    except Exception as e:
        return f"Error en BCP (Selenium): {str(e)[:100]}" # Error resumido
    finally:
        if driver:
            driver.quit()

def tarea_principal():
    """Función que orquesta la ejecución y muestra los resultados."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n--- Actualización: {ahora} ---")
    
    # Ejecución de los tres scrapeos
    print(obtener_datos_bcb())
    print(obtener_datos_bisa())
    print(obtener_datos_bcp())

# --- PROGRAMACIÓN ---
schedule.every(15).minutes.do(tarea_principal)

if __name__ == "__main__":
    print("Iniciando monitor de divisas (BCB, BISA, BCP)...")
    tarea_principal()
    
    while True:
        schedule.run_pending()
        time.sleep(1)