import re
import time
import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler

# --------------------------
# CONFIGURAÇÕES
# --------------------------
GDRIVE_URL = "https://drive.google.com/file/d/11xLQKuz4uicx-SFIr2zLbp9whDSvnXbE/view?usp=drivesdk"
PORTA = 8080
TIMEOUT_TESTE = 10  # ⏱️ Mais tempo para não descartar canais bons
MAX_TENTATIVAS = 3
MAX_THREADS = 15
BUFFER_PARAMS = "buffer=4000000&timeout=10000&reconnect=1"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
lista_pronta = "#EXTM3U\n# Aguardando primeira execução...\n"

def extrair_id_gdrive(url):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None

def link_direto_gdrive(url):
    return f"https://drive.google.com/uc?id={extrair_id_gdrive(url)}&export=download"

def baixar_lista(url):
    headers = {"User-Agent": USER_AGENT}
    for _ in range(MAX_TENTATIVAS):
        try:
            r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.warning(f"Erro download: {e}")
            time.sleep(2)
    raise ValueError("Falha ao baixar lista")

def testar_canal(item):
    inicio = time.perf_counter()
    try:
        h = {"User-Agent": USER_AGENT, "Connection": "keep-alive"}
        resp = requests.head(item["url"], headers=h, timeout=TIMEOUT_TESTE, allow_redirects=True)
        if resp.status_code < 400:
            item["velocidade"] = round(time.perf_counter() - inicio, 3)
            item["ok"] = True
        else:
            item["ok"] = False
    except Exception:
        # Se der erro no HEAD, tenta um GET simples
        try:
            resp = requests.get(item["url"], headers=h, timeout=TIMEOUT_TESTE, stream=True)
            if resp.status_code < 400:
                item["velocidade"] = round(time.perf_counter() - inicio, 3)
                item["ok"] = True
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
        # Captura tanto #EXTINF quanto se vier direto
        if linhas[i].startswith("#EXTINF:"):
            if i + 1 < len(linhas) and linhas[i+1].startswith("http"):
                canais.append({"info": linhas[i], "url": linhas[i+1]})
                i += 2
            else:
                i += 1
        elif linhas[i].startswith("http"):
            # Caso raro: canal sem #EXTINF
            canais.append({"info": '#EXTINF:-1,Canal Sem Nome', "url": linhas[i]})
            i += 1
        else:
            i += 1

    logging.info(f"📺 Total encontrado na lista: {len(canais)} canais")

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
        res = list(ex.map(testar_canal, canais))
    
    bons = sorted([c for c in res if c["ok"]], key=lambda x: x["velocidade"])
    logging.info(f"✅ Total funcionando e rápido: {len(bons)} canais")

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
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(lista_pronta.encode("utf-8"))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK - Acesse /lista.m3u")

def atualizar_loop():
    global lista_pronta
    while True:
        try:
            link = link_direto_gdrive(GDRIVE_URL)
            texto = baixar_lista(link)
            lista_pronta = processar_lista(texto)
            logging.info("🔄 Lista atualizada com sucesso!")
        except Exception as e:
            logging.error(f"❌ Erro geral: {e}")
        time.sleep(6 * 60 * 60)

def iniciar():
    from threading import Thread
    Thread(target=atualizar_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORTA), Servidor).serve_forever()

if __name__ == "__main__":
    iniciar()
