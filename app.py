import re
import os
import time
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler

# --------------------------
# CONFIGURAÇÕES
# --------------------------
GDRIVE_URL = "https://drive.google.com/file/d/11xLQKuz4uicx-SFIr2zLbp9whDSvnXbE/view?usp=drivesdk"
PORTA = int(os.environ.get("PORT", 8080))
MAX_TENTATIVAS = 2
TIMEOUT = 12  # ⏱️ Tempo bom para não descartar canais
MAX_THREADS = 12
# Parâmetros que ajudam na estabilidade
BUFFER_PARAMS = "buffer=5000000&timeout=12000&reconnect=1&user_agent=default"
USER_AGENT = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/128.0.0.0 Mobile Safari/537.36"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
lista_pronta = "#EXTM3U\n# Carregando...\n"

def extrair_id_gdrive(url):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None

def link_direto_gdrive(url):
    return f"https://drive.google.com/uc?id={extrair_id_gdrive(url)}&export=download"

def baixar_lista(url):
    headers = {"User-Agent": USER_AGENT}
    for _ in range(MAX_TENTATIVAS):
        try:
            r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.warning(f"Erro download: {e}")
            time.sleep(3)
    raise ValueError("Falha ao baixar lista")

def testar_canal(item):
    """Testa sem bloquear, tenta HEAD e depois GET"""
    inicio = time.perf_counter()
    url = item["url"]
    headers = {"User-Agent": USER_AGENT, "Connection": "keep-alive", "Accept": "*/*"}
    
    try:
        resp = requests.head(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code < 400:
            item["ok"] = True
            item["velocidade"] = round(time.perf_counter() - inicio, 3)
            return item
    except:
        pass

    # Se HEAD falhar, tenta pegar só o começo do stream
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=True)
        if resp.status_code < 400:
            item["ok"] = True
            item["velocidade"] = round(time.perf_counter() - inicio, 3)
        else:
            item["ok"] = False
    except:
        item["ok"] = False
    return item

def processar_lista(texto):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    if not linhas or not linhas[0].startswith("#EXTM3U"):
        raise ValueError("Lista inválida ou sem cabeçalho")
    
    canais = []
    i = 1
    while i < len(linhas):
        if linhas[i].startswith("#EXTINF:") and i + 1 < len(linhas) and linhas[i+1].startswith("http"):
            canais.append({"info": linhas[i], "url": linhas[i+1]})
            i += 2
        elif linhas[i].startswith("http"):
            canais.append({"info": '#EXTINF:-1,Canal sem nome', "url": linhas[i]})
            i += 1
        else:
            i += 1

    logging.info(f"📺 Total encontrado: {len(canais)} — testando links...")

    # Teste em paralelo
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
        res = list(ex.map(testar_canal, canais))
    
    # Só os bons, ordenados por velocidade
    bons = sorted([c for c in res if c.get("ok")], key=lambda x: x.get("velocidade", 99))
    logging.info(f"✅ Funcionando: {len(bons)} canais — os lentos/quebrados foram removidos")

    saida = ["#EXTM3U"]
    for c in bons:
        sep = "&" if "?" in c["url"] else "?"
        saida.append(c["info"])
        saida.append(f"{c['url']}{sep}{BUFFER_PARAMS}")
    return "\n".join(saida)

class Servidor(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/lista.m3u":
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=21600") # cache 6h
            self.end_headers()
            self.wfile.write(lista_pronta.encode("utf-8"))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK — Acesse /lista.m3u")

def atualizar_loop():
    global lista_pronta
    while True:
        try:
            link = link_direto_gdrive(GDRIVE_URL)
            texto = baixar_lista(link)
            lista_pronta = processar_lista(texto)
            logging.info("🔄 Lista atualizada com sucesso! Apenas canais bons.")
        except Exception as e:
            logging.error(f"❌ Erro: {e}")
        time.sleep(6 * 60 * 60)

def iniciar():
    from threading import Thread
    Thread(target=atualizar_loop, daemon=True).start()
    logging.info(f"🌐 Servidor na porta {PORTA}")
    HTTPServer(("0.0.0.0", PORTA), Servidor).serve_forever()

if __name__ == "__main__":
    iniciar()
