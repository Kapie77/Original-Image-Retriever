# OIR — Original Image Retriever
OIR (Original Image Retriever) is a web application designed to help users retrieve original images from supported URLs. It analyzes image links, identifies image formats, displays previews, and allows users to download images when access is available.

This is a tool for anyone who's tired of trying to download files in .png, .jpg, etc., only to end up with a .WebP file.

It simply looks up the URL of the original format! It is not a .WebP converter!

If the original image is a .WebP file, you'll be notified and the download will be blocked.

~~For now, it only works locally.~~

I was able to host the website for free through [Render](<https://render.com/>).

![release](https://i.ibb.co/WSYjLQM/website.png)
![release2](https://i.ibb.co/v49Sn3vz/website2.png)

# Supported Sources
Initial support includes:

- Fandom and Wikia
- Reddit
- DuckDuckGo
- Direct image URLs, where supported

Availability depends on the source website, access permissions, and the image URL.

Maximum limit: 25 MB.

# How to use it locally
Running Locally

Requirements

- Python 3.11 or another Python version compatible with the project's dependencies.
- pip

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

# About the Project

# Project Structure

Original-Image-Retriever/
├── app.py
├── requirements.txt
├── test_app.py
├── services/
│   ├── image_downloader.py
│   ├── image_detector.py
│   ├── filename_handler.py
│   └── image_resolver.py
├── templates/
│   └── index.html
└── static/
    ├── style.css
    ├── script.js
    └── favicon.png

## Technologies
OIR uses the following technologies:

- Python — Application logic and backend processing.
- Flask — Python web framework responsible for routing requests and serving the web interface.
- Gunicorn — Production WSGI server used to run the Flask application in deployment environments.
- HTML — Web page structure.
- CSS — Styling and responsive layout.
- JavaScript — Client-side interactions and communication with the backend.

## Deployment
OIR can be deployed to a hosting provider that supports Python applications and WSGI servers, such as Render.

## Flask
Flask handles HTTP requests, application routes, and rendering of the HTML templates. It also connects the web interface to the image processing services.

## Gunicorn
Gunicorn is a WSGI HTTP server used to run the Flask application in production. Unlike Flask's built-in development server, Gunicorn is intended for serving deployed applications.

For a Render Web Service, the typical configuration is:

**Build Command**
```bash
pip install -r requirements.txt
```

**Start Command**
```bash
gunicorn app:app
```

The app:app command refers to the Flask application object named app inside app.py.

Gunicorn must be listed in requirements.txt for the deployment environment to install it.

## Limitations
Some websites restrict automated requests or block access to original images.

- Image availability depends on the source server and its access policies.
- WebP downloads are currently unsupported.
- Hosting providers may impose resource, bandwidth, and request limits.

## Security
OIR processes URLs provided by users. A public deployment should validate external URLs, restrict access to internal network resources, limit redirects and download sizes, and apply appropriate resource controls.

## How to open files/folders directly via the terminal
Open the folder in VS Code:
```bash
code .
```

How to open a file using cmd:
```bash
notepad app.py
```
