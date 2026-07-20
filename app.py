import re
import os
import time
import requests
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

# --------------------------
# CONFIGURAÇÕES FIXAS
# --------------------------
GDRIVE_URL = "https://drive.google.com/file/d/11xLQKuz4uicx-SFIr2zLbp9whDSvnXbE/view?usp=drivesdk"
PORTA = int(os.environ.get("PORT", 10000))  # Porta padrão do Render
MAX_TENTATIVAS = 3
BUFFER_PARAMS = "buffer=5000000&timeout=10000&reconnect=1"
USER_AGENT = "Mozilla/5.0"

logging.basicConfig(level=logging.INFO)
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
            r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            logging.warning(f"Tentativa falhou: {e}")
            time.sleep(2)
    raise ValueError("Falha ao baixar do Drive")

def processar_lista(texto):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    if not linhas or not linhas[0].startswith("#EXTM3U"):
        raise ValueError("Lista inválida")
    
    canais = []
    i = 1
    while i < len(linhas):
        if linhas[i].startswith("#EXTINF:") and i+1 < len(linhas) and linhas[i+1].startswith("http"):
            canais.append({"info": linhas[i], "url": linhas[i+1]})
            i += 2
        elif linhas[i].startswith("http"):
            canais.append({"info": '#EXTINF:-1,Canal', "url": linhas[i]})
            i += 1
        else:
            i += 1

    logging.info(f"Encontrados: {len(canais)} canais")

    saida = ["#EXTM3U"]
    for c in canais:
        sep = "&" if "?" in c["url"] else "?"
        saida.append(c["info"])
        saida.append(f"{c['url']}{sep}{BUFFER_PARAMS}")
    return "\n".join(saida)

class MeuServidor(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/lista.m3u":
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(lista_pronta.encode("utf-8"))
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

def atualizar():
    global lista_pronta
    while True:
        try:
            link = link_direto_gdrive(GDRIVE_URL)
            texto = baixar_lista(link)
            lista_pronta = processar_lista(texto)
            logging.info("✅ Lista atualizada!")
        except Exception as e:
            logging.error(f"Erro: {e}")
        time.sleep(6 * 60 * 60)

def iniciar():
    from threading import Thread
    Thread(target=atualizar, daemon=True).start()
    logging.info(f"Rodando na porta {PORTA}")
    HTTPServer(("0.0.0.0", PORTA), MeuServidor).serve_forever()

if __name__ == "__main__":
    iniciar()
