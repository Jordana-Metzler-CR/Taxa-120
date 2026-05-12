import subprocess
import re

def iniciar_tunel():
    processo = subprocess.Popen(
        [
            r"C:\cloudflared\cloudflared.exe",
            "tunnel",
            "--url",
            "http://localhost:5000"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    url_publica = None

    for linha in processo.stdout:
        print(linha.strip())

        match = re.search(r"https://.*?trycloudflare.com", linha)
        if match:
            url_publica = match.group(0)
            break

    if not url_publica:
        raise Exception("Não foi possível obter URL pública")

    return processo, url_publica
