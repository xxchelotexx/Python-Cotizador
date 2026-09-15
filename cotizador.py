import os
import sys
import time
import urllib3
import schedule
import re
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from bs4 import BeautifulSoup
import requests
from curl_cffi import requests as curl_requests

# Configuración de entorno y consola
os.environ['PYTHONUNBUFFERED'] = "1"
if sys.platform == "win32":
    os.system("chcp 65001 > nul")
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
    print("[1/9] Consultando BCB...", flush=True)
    url = "https://www.bcb.gob.bo/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        num_span = soup.find("span", class_=re.compile(r"\bbcb-tco-num\b"))
        if not num_span:
            card = soup.find(class_=re.compile(r"is-tc-oficial"))
            if card:
                num_span = card.find("span", class_=re.compile(r"num"))

        if num_span:
            texto_limpio = num_span.get_text(strip=True)
            match = re.search(r"\d+[\.,]\d+", texto_limpio)

            if match:
                valor_texto = match.group(0).replace(",", ".")
                valor_float = float(valor_texto)

                res = {
                    "venta": round(valor_float + 0.1, 2),
                    "compra": round(valor_float - 0.1, 2),
                    "oficial": valor_float,
                }
                print(f"      OK -> BCB: {res}", flush=True)
                return res

        print("      [!] No se encontró el elemento con clase 'bcb-tco-num' en el HTML.", flush=True)

    except Exception as e:
        print(f"      [!] Error BCB: {e}", flush=True)

    return None

def obtener_datos_bisa():
    print("[2/9] Consultando BISA...", flush=True)
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
    print("[3/9] Consultando BCP (curl_cffi)...", flush=True)
    url = "https://www.bcp.com.bo/"
    headers = {
        "Host": "www.bcp.com.bo",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    try:
        response = curl_requests.get(
            url, 
            headers=headers, 
            impersonate="chrome124", 
            timeout=15
        )
        response.raise_for_status()
        html_content = response.text

        patrones = {
            "USD_compra": r"Dólar Compra:\s*([\d\.,]+)",
            "USD_venta": r"Dólar Venta:\s*([\d\.,]+)",
            "USDT_compra": r"USDT Compra:\s*([\d\.,]+)",
            "USDT_venta": r"USDT Venta:\s*([\d\.,]+)"
        }

        extraidos = {}
        for clave, patron in patrones.items():
            match = re.search(patron, html_content)
            if match:
                extraidos[clave] = float(match.group(1).replace(',', '.'))
            else:
                extraidos[clave] = None

        res_bcp_usdt = {
            "compra": extraidos.get("USDT_compra"),
            "venta": extraidos.get("USDT_venta")
        }
        res_bcp_usd = {
            "compra": extraidos.get("USD_compra"),
            "venta": extraidos.get("USD_venta")
        }

        print(f"      OK -> BCP USDT: {res_bcp_usdt}", flush=True)
        print(f"      OK -> BCP USD : {res_bcp_usd}", flush=True)

        return res_bcp_usdt, res_bcp_usd

    except Exception as e:
        print(f"      [!] Error BCP: {e}", flush=True)
        return {"compra": None, "venta": None}, {"compra": None, "venta": None}

def obtener_datos_baneco():
    print("[4/9] Consultando Banco Económico...", flush=True)
    url = "https://www.baneco.com.bo/gbGLOBALTiposDeCambio"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        data = response.json()
        
        texto = data.get("gbGLOBALTiposDeCambioResult", "")
        
        match_compra = re.search(r"Compra:\s*([\d\.,]+)", texto)
        match_venta = re.search(r"Venta:\s*([\d\.,]+)", texto)
        
        compra = float(match_compra.group(1).replace(',', '.')) if match_compra else None
        venta = float(match_venta.group(1).replace(',', '.')) if match_venta else None
        
        res = {"compra": compra, "venta": venta}
        print(f"      OK -> BANECO (BEC_USD): {res}", flush=True)
        return res

    except Exception as e:
        print(f"      [!] Error Banco Económico: {e}", flush=True)
        return {"compra": None, "venta": None}

def obtener_datos_bmsc():
    print("[5/9] Consultando Banco Mercantil Santa Cruz...", flush=True)
    url = "https://backportal.bmsc.com.bo:1443/api/bmscservices/tipotre"
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        data = response.json()
        
        compra = float(data.get("compra")) if data.get("compra") is not None else None
        venta = float(data.get("venta")) if data.get("venta") is not None else None
        
        res = {"compra": compra, "venta": venta}
        print(f"      OK -> BMSC (BMSC_USD): {res}", flush=True)
        return res

    except Exception as e:
        print(f"      [!] Error Banco Mercantil Santa Cruz: {e}", flush=True)
        return {"compra": None, "venta": None}

def obtener_datos_fie():
    print("[6/9] Consultando Banco FIE...", flush=True)
    url = "https://www.bancofie.com.bo/api/tcl"
    
    headers_fie = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Content-Type': 'application/json',
        'Origin': 'https://www.bancofie.com.bo',
        'Referer': 'https://www.bancofie.com.bo/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

    try:
        response = requests.post(url, headers=headers_fie, json={}, verify=False, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        doc_texto = data.get("resultado", {}).get("documento", "")
        
        match_compra = re.search(r"Dólar Compra:\s*([\d\.,]+)", doc_texto)
        match_venta = re.search(r"Dólar Venta:\s*([\d\.,]+)", doc_texto)
        
        compra = float(match_compra.group(1).replace(',', '.')) if match_compra else None
        venta = float(match_venta.group(1).replace(',', '.')) if match_venta else None
        
        res = {"compra": compra, "venta": venta}
        print(f"      OK -> FIE (FIE_USD): {res}", flush=True)
        return res

    except Exception as e:
        print(f"      [!] Error Banco FIE: {e}", flush=True)
        return {"compra": None, "venta": None}

def obtener_datos_bsol():
    print("[7/9] Consultando BancoSol...", flush=True)
    url = "https://www.bancosol.com.bo/"
    
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        p_tag = soup.find(lambda tag: tag.name == 'p' and 'Tipo de cambio compra' in tag.text)
        
        compra, venta = None, None
        if p_tag:
            texto = p_tag.get_text()
            match_compra = re.search(r"compra:\s*([\d\.,]+)", texto, re.IGNORECASE)
            match_venta = re.search(r"venta\s*:\s*([\d\.,]+)", texto, re.IGNORECASE)
            
            if match_compra:
                compra = float(match_compra.group(1).replace(',', '.'))
            if match_venta:
                venta = float(match_venta.group(1).replace(',', '.'))

        res = {"compra": compra, "venta": venta}
        print(f"      OK -> BancoSol (BSOL_USD): {res}", flush=True)
        return res

    except Exception as e:
        print(f"      [!] Error BancoSol: {e}", flush=True)
        return {"compra": None, "venta": None}

def obtener_datos_bnb():
    print("[8/9] Consultando Banco Nacional de Bolivia (BNB)...", flush=True)
    url = "https://www.bnb.com.bo/PortalBNB/Principal/BancaPersonas"
    
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        datos = {"compra": None, "venta": None}
        spans = soup.find_all('span')
        
        for i, s in enumerate(spans):
            texto = s.get_text(strip=True)
            if "Dólar Compra" in texto and i + 1 < len(spans):
                val_text = spans[i + 1].get_text(strip=True).replace(',', '.')
                match = re.search(r"[\d\.,]+", val_text)
                if match:
                    datos["compra"] = float(match.group(0))
            elif "Dólar Venta" in texto and i + 1 < len(spans):
                val_text = spans[i + 1].get_text(strip=True).replace(',', '.')
                match = re.search(r"[\d\.,]+", val_text)
                if match:
                    datos["venta"] = float(match.group(0))

        print(f"      OK -> BNB (BNB_USD): {datos}", flush=True)
        return datos

    except Exception as e:
        print(f"      [!] Error BNB: {e}", flush=True)
        return {"compra": None, "venta": None}

def obtener_datos_bun():
    print("[9/9] Consultando Banco Unión...", flush=True)
    url = "https://bancounion.com.bo/"
    
    try:
        response = requests.get(url, headers=HEADERS, verify=False, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        datos = {"compra": None, "venta": None}
        p_tag = soup.find(lambda tag: tag.name == 'p' and 'Compra BOB:' in tag.text)
        
        if p_tag:
            texto = p_tag.get_text()
            match_compra = re.search(r"Compra\s+BOB:\s*([\d\.,]+)", texto, re.IGNORECASE)
            match_venta = re.search(r"Venta\s*:?\s*([\d\.,]+)", texto, re.IGNORECASE)
            
            if match_compra:
                datos["compra"] = float(match_compra.group(1).replace(',', '.'))
            if match_venta:
                datos["venta"] = float(match_venta.group(1).replace(',', '.'))

        print(f"      OK -> Banco Unión (BUN_USD): {datos}", flush=True)
        return datos

    except Exception as e:
        print(f"      [!] Error Banco Unión: {e}", flush=True)
        return {"compra": None, "venta": None}

def tarea_principal():
    ahora = datetime.now()
    print(f"\n--- INICIO DE CICLO: {ahora.strftime('%H:%M:%S')} ---", flush=True)
    
    # Ejecución de los Scrapers
    res_bcb = obtener_datos_bcb()
    res_bisa = obtener_datos_bisa()
    res_bcp_usdt, res_bcp_usd = obtener_datos_bcp()
    res_bec_usd = obtener_datos_baneco()
    res_bmsc_usd = obtener_datos_bmsc()
    res_fie_usd = obtener_datos_fie()
    res_bsol_usd = obtener_datos_bsol()
    res_bnb_usd = obtener_datos_bnb()
    res_bun_usd = obtener_datos_bun()  # <--- Nuevo: Banco Unión

    # Preparar el documento estructurado
    documento = {
        "timestamp": ahora,
        "fuentes": {
            "BCB": res_bcb,
            "BISA": res_bisa,
            "BCP_USDT": res_bcp_usdt,
            "BCP_USD": res_bcp_usd,
            "BEC_USD": res_bec_usd,
            "BMSC_USD": res_bmsc_usd,
            "FIE_USD": res_fie_usd,
            "BSOL_USD": res_bsol_usd,
            "BNB_USD": res_bnb_usd,
            "BUN_USD": res_bun_usd     # <--- Nuevo: Registro en MongoDB
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