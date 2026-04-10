import os
import sys
import time
import urllib3
import schedule
import io
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

# Scrapers
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuración de entorno y consola
os.environ['PYTHONUNBUFFERED'] = "1"
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_mongo_client():
    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASS")
    cluster = os.getenv("MONGO_CLUSTER")
    if not all([user, password, cluster]):
        print("[DB] ERROR: Faltan credenciales en .env", flush=True)
        return None
    uri = f"mongodb+srv://{user}:{password}@{cluster}/?retryWrites=true&w=majority"
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client["Monitor_P2P_Bolivia"]["FIAT_PRICE"]

def obtener_datos_bcb():
    print("[1/3] Consultando BCB...", flush=True)
    url = "https://www.bcb.gob.bo/"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        cards = soup.find_all('article', class_='bcb-kpi2-card')
        for card in cards:
            titulo = card.find('p', class_='bcb-kpi2-name')
            if titulo and "Valor referencial" in titulo.text:
                vals = card.find_all('div', class_='bcb-val')
                res = {
                    "compra": float(vals[0].get_text(strip=True).replace(',', '.')),
                    "venta": float(vals[1].get_text(strip=True).replace(',', '.'))
                }
                print(f"      OK -> BCB: {res}", flush=True)
                return res
    except Exception as e:
        print(f"      [!] Error BCB: {e}", flush=True)
    return None

def obtener_datos_bisa():
    print("[2/3] Consultando BISA...", flush=True)
    url = "https://www.bisa.com/home"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        spans = soup.find_all('span')
        datos = {"compra": None, "venta": None}
        for s in spans:
            texto = s.get_text(strip=True)
            if "USDTs Compra" in texto:
                datos["compra"] = float(texto.replace("USDTs Compra", "").strip().replace(',', '.'))
            elif "USDTs Venta" in texto:
                datos["venta"] = float(texto.replace("USDTs Venta", "").strip().replace(',', '.'))
        print(f"      OK -> BISA: {datos}", flush=True)
        return datos
    except Exception as e:
        print(f"      [!] Error BISA: {e}", flush=True)
    return None

def obtener_datos_bcp():
    print("[3/3] Consultando BCP (Selenium)...", flush=True)
    url = "https://www.bcp.com.bo/"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)
        wait = WebDriverWait(driver, 25)

        # Intento de cerrar popup
        try:
            btn_cerrar = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "cerrarBtn1")))
            btn_cerrar.click()
        except:
            pass

        wait.until(lambda d: "USDT Venta" in d.find_element(By.CLASS_NAME, "marquee-content").text)
        contenido = driver.execute_script("return document.querySelector('.marquee-content').innerText;")
        
        partes = contenido.split('|')
        for parte in partes:
            if "USDT Venta" in parte:
                valor = float(parte.replace("USDT Venta:", "").strip().replace(',', '.'))
                print(f"      OK -> BCP: {valor}", flush=True)
                return {"venta": valor}
    except Exception as e:
        print(f"      [!] Error BCP: {str(e)[:50]}...", flush=True)
    finally:
        if driver: driver.quit()
    return None

def tarea_principal():
    ahora = datetime.now()
    print(f"\n--- INICIO DE CICLO: {ahora.strftime('%H:%M:%S')} ---", flush=True)
    
    # Ejecución de los Scrapers
    res_bcb = obtener_datos_bcb()
    res_bisa = obtener_datos_bisa()
    res_bcp = obtener_datos_bcp()

    # Preparar el documento
    documento = {
        "timestamp": ahora,
        "fuentes": {
            "BCB": res_bcb,
            "BISA": res_bisa,
            "BCP": res_bcp
        }
    }

    # Guardar en MongoDB
    print("[DB] Conectando y guardando...", flush=True)
    try:
        coleccion = get_mongo_client()
        if coleccion is not None:
            ins_res = coleccion.insert_one(documento)
            print(f"[DB] EXITO: Insertado ID {ins_res.inserted_id}", flush=True)
    except Exception as e:
        print(f"[DB] ERROR: {e}", flush=True)

    print(f"--- FIN DE CICLO: {datetime.now().strftime('%H:%M:%S')} ---\n", flush=True)

# --- PROGRAMACIÓN ---
schedule.every(15).minutes.do(tarea_principal)

if __name__ == "__main__":
    print("SISTEMA: Monitor de Divisas Bolivia Activo", flush=True)
    tarea_principal()
    
    while True:
        schedule.run_pending()
        time.sleep(1)