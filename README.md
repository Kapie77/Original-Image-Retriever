# Original Image Retriever
This is a tool for anyone who's tired of trying to download files in .png, .jpg, etc., only to end up with a .WebP file.
It simply looks up the URL of the original format! It is not a .WebP converter!
If the original image is a .WebP file, you'll be notified and the download will be blocked.
For now, it only works locally.

![release](https://i.ibb.co/WSYjLQM/website.png)

# Websites suportados
- Reddit
- DuckDuckGo
- Wikia
- Fandom

Limite máximo: 25MB.

# Como usar localmente
Acesse a pasta do OIR:
```bash
cd /d "%USERPROFILE%\Documents\OriginalImageRetriever"
```

Abra um servidor python (é preciso ter o python instalado):
```bash
python app.py
```

Para parar/reiniciar digite:
```bash
ctrl + c
```

URL do servidor/website:
http://127.0.0.1:5000/

## Como abrir os arquivos/pasta diretamente via terminal
Abra a pasta no VS Code:
```bash
code .
```

Como abrir um arquivo via cmd:
```bash
notepad app.py
```
