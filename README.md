# Original Image Retriever
This is a tool for anyone who's tired of trying to download files in .png, .jpg, etc., only to end up with a .WebP file.
It simply looks up the URL of the original format! It is not a .WebP converter!
If the original image is a .WebP file, you'll be notified and the download will be blocked.
~~For now, it only works locally.~~
I was able to host the website for free through [Render](<https://render.com/>).

![release](https://i.ibb.co/WSYjLQM/website.png)
![release2](https://i.ibb.co/v49Sn3vz/website2.png)

# Supported Websites
- Reddit
- DuckDuckGo
- Wikia
- Fandom

Maximum limit: 25 MB.

# How to use it locally
Access the OIR folder, example:
```bash
cd /d "%USERPROFILE%\Documents\OriginalImageRetriever"
```

Start a Python server (you must have Python installed):
```bash
python app.py
```

To stop/restart, type:
```bash
ctrl + c
```

Server/website URL:
http://127.0.0.1:5000/

## How to open files/folders directly via the terminal
Open the folder in VS Code:
```bash
code .
```

How to open a file using cmd:
```bash
notepad app.py
```
