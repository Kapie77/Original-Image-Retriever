// script.js
// static/

const urlInput = document.querySelector("#image-url");
const analyzeButton = document.querySelector("#analyze-button");

const message = document.querySelector("#message");
const result = document.querySelector("#result");

const preview = document.querySelector("#preview");
const formatLabel = document.querySelector("#format");
const sizeLabel = document.querySelector("#size");
const dimensionsLabel = document.querySelector("#dimensions");
const statusLabel = document.querySelector("#result-status");
const notice = document.querySelector("#notice");
const downloadButton = document.querySelector("#download-button");

// Displays a general message in the interface.
function showMessage(text, isError = false) {
    message.textContent = text;
    message.classList.remove("hidden", "error");

    if (isError) {
        message.classList.add("error");
    }
}

// Hides the general message.
function hideMessage() {
    message.classList.add("hidden");
}

// Formats the file size for easier reading.
function formatBytes(bytes) {
    if (bytes < 1024) {
        return `${bytes} bytes`;
    }

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

// Updates the image dimensions after it loads.
function readDimensions(image) {
    dimensionsLabel.textContent =
        `${image.naturalWidth} × ${image.naturalHeight}`;
}

// Disables the download button and displays a warning.
function disableDownload(messageText) {
    downloadButton.removeAttribute("href");
    downloadButton.removeAttribute("download");

    downloadButton.classList.add("disabled");
    downloadButton.setAttribute("aria-disabled", "true");
    downloadButton.setAttribute("tabindex", "-1");

    downloadButton.textContent = "Download Unavailable";

    notice.textContent = messageText;
    notice.classList.add("notice-warning");
}

// Enables the download button for supported formats.
function enableDownload(downloadUrl, extension) {
    downloadButton.href = downloadUrl;
    downloadButton.download = `original-image.${extension}`;

    downloadButton.classList.remove("disabled");
    downloadButton.setAttribute("aria-disabled", "false");
    downloadButton.removeAttribute("tabindex");

    downloadButton.textContent = "Download Image";

    notice.classList.remove("notice-warning");
}

// Analyzes the image URL provided by the user.
async function analyzeImage() {
    const url = urlInput.value.trim();

    if (!url) {
        showMessage("Please enter an image URL.", true);
        return;
    }

    hideMessage();
    result.classList.add("hidden");

    // Clears the previous analysis results.
    preview.removeAttribute("src");

    downloadButton.removeAttribute("href");
    downloadButton.removeAttribute("download");
    downloadButton.classList.remove("disabled", "notice-warning");
    downloadButton.setAttribute("aria-disabled", "true");
    downloadButton.setAttribute("tabindex", "-1");
    downloadButton.textContent = "Analyzing...";

    analyzeButton.disabled = true;
    analyzeButton.textContent = "Analyzing...";

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body: JSON.stringify({ url }),
        });

        // Reads the response as text to handle invalid responses
        // without causing unexpected JSON.parse errors.
        const responseText = await response.text();

        let data;

        try {
            data = JSON.parse(responseText);
        } catch {
            console.error(
                "The backend returned a response that is not valid JSON:",
                response.status,
                responseText
            );

            throw new Error(
                `The server returned an invalid response (HTTP ${response.status}). ` +
                "Check the Flask terminal and browser console for details."
            );
        }

        // Handles WebP URLs whose servers reject access with HTTP 403.
        // The format is inferred from the URL, not verified from image bytes.
        if (data.webp_unverified) {
            formatLabel.textContent = "WebP (Unverified)";
            sizeLabel.textContent = "Unavailable";
            dimensionsLabel.textContent = "Unavailable";
            statusLabel.textContent = "Possible WebP — Access Denied";

            preview.onload = () => readDimensions(preview);

            preview.onerror = () => {
                dimensionsLabel.textContent = "Unavailable";
            };

            preview.src = data.preview_url;

            disableDownload(
                "⚠️ This URL appears to point to a WebP image, but the server " +
                "returned HTTP 403. The actual image format could not be verified. " +
                "Downloading is disabled because OIR does not automatically " +
                "convert WebP images."
            );

            result.classList.remove("hidden");
            return;
        }

        if (!response.ok) {
            throw new Error(
                data.error ||
                `Unable to analyze the image (HTTP ${response.status}).`
            );
        }

        // Updates the information displayed in the interface.
        formatLabel.textContent = data.format;
        sizeLabel.textContent = formatBytes(data.size);
        dimensionsLabel.textContent = "Loading...";

        preview.onload = () => readDimensions(preview);

        preview.onerror = () => {
            dimensionsLabel.textContent = "Unavailable";
        };

        // The preview remains available even when the image is WebP.
        preview.src = data.preview_url;

        // Specifically handles images that are still in WebP format.
        if (data.format.toLowerCase() === "webp") {
            statusLabel.textContent = "WebP Detected";

            disableDownload(
                "⚠️ The original image may be in WebP format. " +
                "The server returned a WebP file, and OIR does not " +
                "automatically convert images. The download has been " +
                "disabled. The image preview remains available."
            );

        } else {
            // Formats other than WebP can be downloaded.
            // The extension comes from the actual format identified by the backend.
            enableDownload(data.download_url, data.extension);

            if (data.requested_original) {
                statusLabel.textContent = "Original Format Requested";

                notice.textContent =
                    "The server accepted the request for the original version. " +
                    "This does not guarantee that the file is exactly the one uploaded by its creator.";

            } else {
                statusLabel.textContent = "Alternative Version";

                notice.textContent =
                    "The original version could not be confirmed. " +
                    (data.original_error || "") +
                    " The displayed image corresponds to the alternative file that was found.";
            }
        }

        result.classList.remove("hidden");

    } catch (error) {
        console.error("Error analyzing the image:", error);
        showMessage(error.message, true);

    } finally {
        analyzeButton.disabled = false;
        analyzeButton.textContent = "Analyze Image";
    }
}

// Prevents download attempts when the button is disabled.
downloadButton.addEventListener("click", event => {
    if (downloadButton.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
    }
});

// Starts the analysis when the button is clicked.
analyzeButton.addEventListener("click", analyzeImage);

// Allows the user to start the analysis by pressing Enter in the URL field.
urlInput.addEventListener("keydown", event => {
    if (event.key === "Enter") {
        analyzeImage();
    }
});