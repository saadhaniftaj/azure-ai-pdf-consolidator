# Project Documentation: PDF Data Extraction and Consolidation Web Application

This document provides comprehensive documentation for the PDF data extraction and consolidation project, which utilizes Azure Document Intelligence to process multiple PDF files and consolidate the extracted information into a single, sorted Excel file via a web interface.

## 1. Azure Document Intelligence Custom Model

**Purpose:** The core of the data extraction relies on a custom-trained Azure Document Intelligence model. This model is trained to understand the specific structure and layout of your PDF documents, enabling it to accurately identify and extract key information, particularly the table data and the "Carton ID" field.

**Details:**
*   **Model ID:** The application uses a specific custom model ID, referred to as `"customscan"` in the code. This ID corresponds to the model you trained in Azure Document Intelligence Studio.
*   **Extraction:** The model is configured to extract structured data from tables and identify specific fields like the "Carton ID". The `extract_table_data` function in the Python code is designed based on the expected output structure of this custom model, specifically targeting columns for BARCODE, ARTICLE, PRICE, and QUANTITY within a main data table, and retrieving the Carton ID from a dedicated field.

**Training:** (This part is assumed to have been done by you in Azure Document Intelligence Studio)
To use this application, you must have:
1.  Created an Azure Document Intelligence resource.
2.  Trained a custom extraction model (a custom template or custom neural model) specifically on examples of your PDF documents.
3.  Ensured the model correctly identifies the main data table containing product details and a distinct field for the "Carton ID".
4.  Obtained the **Endpoint** and **API Key** for your Azure Document Intelligence resource and the **Model ID** of your trained custom model.

## 2. Local Processing Script (`local.py`)

**Purpose:** The `local.py` script was the initial tool developed to test the Azure Document Intelligence model and the core data extraction and consolidation logic on your local machine. It processes PDF files from a local directory and outputs a consolidated Excel file.

**Key Components & Logic:**

*   **Azure Client Initialization:** Initializes the `DocumentAnalysisClient` using endpoint and key loaded from environment variables (`.env` file).
*   **PDF Analysis (`analyze_pdf` function):**
    *   Takes a single PDF file path as input.
    *   Opens and reads the PDF file in binary mode.
    *   Calls `begin_analyze_document` on the Azure client with the custom model ID.
    *   Polls the Azure service for the analysis result, waiting until it's complete or a timeout is reached.
    *   Handles potential `HttpResponseError` (e.g., rate limiting) and other exceptions during the analysis process.
*   **Data Extraction (`extract_table_data` function):**
    *   Takes the analysis `result` from Azure as input.
    *   Extracts the "Carton ID" from the dedicated field identified by the custom model. Includes logic to handle cases where the field might be missing or empty.
    *   Identifies the main data table. It uses a heuristic to select the table with the most cells if multiple tables are detected, assuming this is the main product data table.
    *   Iterates through the cells of the main table, grouping them by row.
    *   Maps specific column indices (based on your model's table structure) to desired output headers (BARCODE, ARTICLE, PRICE, QUANTITY).
    *   Includes special handling for the PRICE column to ensure it's formatted correctly (e.g., adding "DHS" if missing).
    *   Combines the extracted field-level Carton ID with each data row from the table.
    *   Filters out potentially empty or invalid rows.
    *   Returns a list of dictionaries, where each dictionary represents a processed data row.
*   **File Iteration and Consolidation:** The main part of the script iterates through all `.pdf` files in the current directory, calls `analyze_pdf` for each, and collects the extracted data into a single list.
*   **Sorting:** The consolidated data is then sorted numerically by the "Carton ID" column using pandas. A fallback to string sorting is included if numerical conversion fails.
*   **Excel Output:** The sorted data is saved to an Excel file named `consolidatedfile.xlsx` using pandas.

**Local Testing:**
The `local.py` script was used for initial testing by placing sample PDF files in the same directory and running the script from the terminal:
```bash
python local.py
```
This allowed verification of:
*   Correct Azure credential setup (`.env`).
*   Successful communication with Azure Document Intelligence.
*   Accurate data extraction based on the custom model.
*   Correct table parsing and row extraction.
*   Proper handling and association of Carton IDs.
*   Successful data consolidation and sorting.
*   Generation of the final Excel output file.

## 3. Web Application (`app.py`)

**Purpose:** The `app.py` file transforms the core processing logic into a web application using FastAPI, allowing users to upload multiple PDF files concurrently via a web interface and receive a single consolidated Excel file in return.

**Key Components & Logic:**

*   **FastAPI Framework:** Builds a web API with asynchronous capabilities, suitable for handling multiple concurrent requests.
*   **Endpoints:**
    *   `GET /`: Serves the HTML web interface (`index.html`) using Jinja2 templates.
    *   `POST /process_pdfs/`: Accepts multiple file uploads, processes them, and returns the consolidated Excel file.
*   **Dependency Imports:** Imports necessary libraries for FastAPI, file handling, data processing (pandas), Azure interaction, environment variables, and template rendering (Jinja2).
*   **Azure Configuration:** Loads Azure credentials from environment variables (which will be set as Application Settings on Azure).
*   **Temporary File Handling:**
    *   Uploaded files are saved temporarily on the server's disk using `tempfile.NamedTemporaryFile`.
    *   The temporary PDF files are automatically cleaned up after processing (handled within a `finally` block).
    *   The final consolidated Excel file is also created as a temporary file before being sent as a response. Cleanup of this file after the response is sent relies on the operating system or further configuration (e.g., a background task for long-running apps).
*   **Multi-file Processing:** The `/process_pdfs/` endpoint iterates through the list of uploaded files.
*   **Integration of Logic:** The core extraction logic from `local.py` is encapsulated in the `analyze_pdf_from_path` helper function within `app.py`. This function is called for each temporary uploaded PDF file.
*   **Data Accumulation:** Extracted data from each processed file is collected into a single list (`all_extracted_data`).
*   **Consolidation and Sorting:** After all files are processed, the `all_extracted_data` list is converted to a pandas DataFrame, and the data is sorted by 'Carton ID' (numerically, with a string fallback) before generating the Excel file.
*   **Error Handling and Fault Tolerance:**
    *   Includes `try...except` blocks around file processing and Azure calls.
    *   Logs errors for individual file processing failures.
    *   Crucially, it continues processing other files even if one file encounters an error, ensuring the entire batch isn't stopped by a single problematic file.
    *   Returns appropriate HTTP error responses (e.g., 400 if no data extracted, 500 for server errors).
*   **Response:** Returns the consolidated Excel file using FastAPI's `FileResponse`.

## 4. Web Interface (`templates/index.html`)

**Purpose:** Provides a user-friendly HTML page allowing users to easily select and upload multiple PDF files through their web browser.

**Key Components:**

*   **HTML Structure:** A simple page layout with a container, a heading, a description, a file upload form, and a status area.
*   **Heading:** Displays "NISSI FULFILLMENT & DISTRIBUTION" as the main title.
*   **Description:** Explains the purpose of the application and how the output will be provided ("Upload your PDF files below... The download will start automatically upon completion.").
*   **File Input:** An `<input type="file">` element configured with `multiple` (to allow selecting multiple files) and `accept=".pdf"` (to suggest PDF files).
*   **Submit Button:** Triggers the file upload and processing.
*   **Status Area (`#status`):** A `div` element where messages are displayed to the user, indicating the processing status (uploading, processing, success, error) and showing the download status.
*   **JavaScript:** Client-side script to:
    *   Listen for the form submission event.
    *   Prevent the default browser form submission.
    *   Gather the selected files using `FormData`.
    *   Make an asynchronous HTTP POST request to the `/process_pdfs/` endpoint with the file data.
    *   Update the `#status` div with messages based on the response from the server (processing, success, error).
    *   If successful, receive the Excel file as a blob and programmatically trigger a download.
    *   Handle potential network errors or errors returned by the FastAPI application.

## 5. Dependencies (`requirements.txt`)

**Purpose:** Lists all the Python packages required for the project to run. This file is used by tools like `pip` and cloud platforms like Azure App Services to automatically install the necessary libraries.

**Required Packages:**

*   `fastapi`: The web framework for building the API.
*   `uvicorn`: An ASGI server, required to run the asynchronous FastAPI application. Used by Gunicorn with the Uvicorn worker class.
*   `gunicorn`: A powerful WSGI HTTP server that can run ASGI applications using compatible worker classes (like Uvicorn). Often used for production deployment.
*   `pandas`: Used for data manipulation and creating the Excel file.
*   `openpyxl`: A dependency for pandas to read/write `.xlsx` files.
*   `azure-ai-formrecognizer`: The Azure SDK for interacting with the Document Intelligence service.
*   `python-dotenv`: Used to load environment variables from a `.env` file (useful for local development).
*   `jinja2`: A templating engine used by FastAPI to render HTML files.
*   `python-multipart`: Required by FastAPI to parse form data, including file uploads.

The `requirements.txt` file should contain these packages, ideally with version specifiers for reproducibility (e.g., `package_name==x.y.z`).

```
fastapi
uvicorn
gunicorn
pandas
openpyxl
azure-ai-formrecognizer
python-dotenv
jinja2
python-multipart
# (Optional/Potentially leftover dependencies like flask, azure-storage-blob, Werkzeug can be removed if not used elsewhere)
```

## 6. Environment Variables

**Purpose:** To securely configure sensitive information required by the application, such as Azure credentials.

*   **`FORM_RECOGNIZER_ENDPOINT`**: The endpoint URL for your Azure Document Intelligence resource.
*   **`FORM_RECOGNIZER_KEY`**: The API key for your Azure Document Intelligence resource.

**Local Development:** Use a `.env` file in the project root directory:
```env
FORM_RECOGNIZER_ENDPOINT="YOUR_AZURE_ENDPOINT"
FORM_RECOGNIZER_KEY="YOUR_AZURE_KEY"
```
*(Replace placeholders with your actual credentials. This file should NOT be committed to version control if it contains secrets).

**Azure Deployment:** Configure these as **Application Settings** in your Azure Web App's Configuration settings in the Azure portal. This injects them as environment variables at runtime securely.

## 7. Deployment on Azure App Service

**Process:** Deploy the application files to an Azure App Service configured with a Python runtime.

**Files to Upload:**
*   `app.py`
*   `requirements.txt`
*   The entire `templates` directory, including `index.html` inside it.

**Key Configuration in Azure Portal:**

*   **Runtime Stack:** Select the appropriate Python version (e.g., Python 3.9 or 3.10).
*   **Application Settings:** Add `FORM_RECOGNIZER_ENDPOINT` and `FORM_RECOGNIZER_KEY`.
*   **Startup Command:** Set the command to instruct Gunicorn to run the FastAPI application using the Uvicorn worker:
    ```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app --bind=0.0.0.0 --timeout 180
```
    *(Adjust `-w` for the number of workers and `--timeout` as needed).

**Deployment Methods:** Common methods include Zip Deploy via Azure CLI, Local Git deployment, or integration with CI/CD pipelines (Azure DevOps, GitHub Actions, etc.).

## 8. Workflow Summary

1.  User opens the web app URL in a browser, which loads `index.html`.
2.  User selects one or more PDF files using the form and clicks "Process Files".
3.  The browser sends the files to the `/process_pdfs/` endpoint on the Azure Web App.
4.  The FastAPI application receives the files and processes each one:
    *   Saves file temporarily.
    *   Calls Azure Document Intelligence via the SDK to analyze the PDF.
    *   Extracts data (Carton ID and table data) from the analysis result.
    *   Cleans up the temporary PDF.
5.  All extracted data is consolidated into a pandas DataFrame.
6.  The DataFrame is sorted by Carton ID.
7.  The sorted data is saved to a temporary Excel file.
8.  The Excel file is sent back to the user's browser as a downloadable file.
9.  The temporary Excel file is eventually cleaned up.
10. The user's browser initiates the download of `consolidated_output.xlsx`.

## 9. Troubleshooting Common Deployment Issues

Based on the logs encountered:

*   **`RuntimeError: Form data requires "python-multipart" to be installed.`**:
    *   **Cause:** The `python-multipart` library, required by FastAPI for form/file uploads, was not installed.
    *   **Solution:** Add `python-multipart` to `requirements.txt` and redeploy.

*   **`TypeError: FastAPI.__call__() missing 1 required positional argument: 'send'`**:
    *   **Cause:** The server (Gunicorn) was attempting to run the FastAPI (ASGI) application using a default WSGI configuration, which is incompatible. This was potentially due to Azure's auto-detection or an incorrect startup command.
    *   **Solution:** Ensure the Azure Web App's **Startup Command** is explicitly set to `gunicorn -w X -k uvicorn.workers.UvicornWorker app:app --bind=0.0.0.0 --timeout Y` (replacing X and Y) to force Gunicorn to use the ASGI-compatible Uvicorn worker. Removing unrelated dependencies like Flask and Werkzeug from `requirements.txt` can also help prevent incorrect auto-detection.

*   **`ModuleNotFoundError: No module named 'uvicorn'`**:
    *   **Cause:** The `uvicorn` package was not installed, even though the startup command required the `uvicorn.workers.UvicornWorker`.
    *   **Solution:** Add `uvicorn` explicitly to `requirements.txt` and redeploy.

By following this documentation, you should have a clear understanding of the project components, how they work together, and how to deploy and troubleshoot the application on Azure App Service. 