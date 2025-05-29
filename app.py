from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import os
import logging
import tempfile
from typing import List
from dotenv import load_dotenv
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

load_dotenv()

form_recognizer_endpoint = os.environ.get("FORM_RECOGNIZER_ENDPOINT")
form_recognizer_key = os.environ.get("FORM_RECOGNIZER_KEY")
custom_model_id = "customscan"

if not form_recognizer_endpoint or not form_recognizer_key:
    logger.error("Azure credentials not found. Please set FORM_RECOGNIZER_ENDPOINT and FORM_RECOGNIZER_KEY in your .env file.")

def extract_table_data(result):
    all_extracted_data = []
    carton_id = 'N/A'
    main_data_table = None
    if not result:
        logger.warning("No analysis result provided to extract_table_data.")
        return []
    try:
        if result.documents and result.documents[0].fields and 'carton id' in result.documents[0].fields:
            carton_id_field = result.documents[0].fields['carton id']
            if carton_id_field.content and carton_id_field.content.strip():
                carton_id = carton_id_field.content.strip()
            elif carton_id_field.value and str(carton_id_field.value).strip():
                carton_id = str(carton_id_field.value).strip()
            else:
                carton_id = 'N/A'
        else:
            carton_id = 'N/A'
    except Exception as e:
        logger.error(f"Error extracting Carton ID from field: {e}", exc_info=True)
        carton_id = 'N/A'
    if not result.tables:
        logger.warning("No tables found in the analysis result.")
        return []
    if len(result.tables) > 1:
        main_data_table = max(result.tables, key=lambda t: len(t.cells), default=None)
        if not main_data_table:
            logger.error("Could not identify a main data table among multiple tables.")
            return []
    else:
        main_data_table = result.tables[0]
    if not main_data_table:
        logger.error("Main data table not found or identified.")
        return []
    try:
        rows_cells_grouped = {}
        for cell in main_data_table.cells:
            row_index = cell.row_index
            col_index = cell.column_index
            cell_content = cell.content.strip()
            if row_index not in rows_cells_grouped:
                rows_cells_grouped[row_index] = {}
            rows_cells_grouped[row_index][col_index] = cell_content
        column_mapping = {
            1: 'BARCODE',
            2: 'ARTICLE',
            7: 'PRICE',
            3: 'QUANTITY'
        }
        all_extracted_data = []
        data_row_indices = sorted([idx for idx in rows_cells_grouped.keys() if idx != 0])
        if not data_row_indices:
            logger.warning("No data rows found after skipping row 0 in extract_table_data.")
            return []
        for row_index in data_row_indices:
            row_cells = rows_cells_grouped[row_index]
            row_data = {}
            row_data['Carton ID'] = carton_id
            for mapped_col_index, header in column_mapping.items():
                cell_content = rows_cells_grouped.get(row_index, {}).get(mapped_col_index, '')
                if header == 'PRICE':
                    if cell_content and not str(cell_content).strip().upper().startswith('DHS'):
                        try:
                            float(cell_content.strip().replace(',',''))
                            cell_content = f"DHS {str(cell_content).strip()}"
                        except ValueError:
                            pass
                row_data[header] = str(cell_content).strip()
            row_data['Scan Count'] = ''
            if row_data.get('BARCODE', '').strip() or row_data.get('ARTICLE', '').strip():
                all_extracted_data.append(row_data)
            else:
                logger.warning(f"Skipped invalid data row: {row_data}")
        return all_extracted_data
    except Exception as e:
        logger.error(f"Error extracting data from analysis result: {e}", exc_info=True)
        return []

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process_pdfs/")
async def process_pdfs(files: List[UploadFile] = File(...)):
    logger.info(f"Received {len(files)} files for processing.")
    all_extracted_data = []
    processed_file_count = 0
    for file in files:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            logger.info(f"Processing file: {file.filename}")
            extracted_data = analyze_pdf_from_path(tmp_file_path)
            if extracted_data:
                all_extracted_data.extend(extracted_data)
                logger.info(f"Successfully extracted data from {file.filename}.")
            else:
                logger.warning(f"No data extracted or error occurred for {file.filename}.")
            processed_file_count += 1
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}", exc_info=True)
        finally:
            if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
                try:
                    os.remove(tmp_file_path)
                except Exception as e:
                    logger.error(f"Error cleaning up temporary file {tmp_file_path}: {e}", exc_info=True)
    if not all_extracted_data:
        logger.warning("No data extracted from any of the uploaded files.")
        raise HTTPException(status_code=400, detail="No data could be extracted from the provided files. Please check the files and try again.")
    try:
        df = pd.DataFrame(all_extracted_data)
        if 'Carton ID' in df.columns:
            try:
                df['Carton ID_numeric'] = pd.to_numeric(df['Carton ID'], errors='coerce')
                df = df.sort_values(by='Carton ID_numeric', na_position='first').drop(columns=['Carton ID_numeric']).reset_index(drop=True)
                logger.info("Consolidated data sorted by Carton ID (numerically).")
            except Exception as numeric_sort_error:
                logger.warning(f"Numerical sort failed ({numeric_sort_error}). Falling back to string sort for Carton ID.")
                df = df.sort_values(by='Carton ID', na_position='first').reset_index(drop=True)
                logger.info("Consolidated data sorted by Carton ID (string).")
        else:
            logger.warning("'Carton ID' column not found in extracted data. Skipping sort.")
    except Exception as e:
        logger.error(f"Error consolidating or sorting data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error consolidating or sorting the extracted data.")
    output_filename = "consolidated_output.xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_excel_file:
        output_filepath = tmp_excel_file.name
    try:
        df.to_excel(output_filepath, index=False)
        logger.info(f"Consolidated data saved to {output_filepath}")
        return FileResponse(path=output_filepath, filename=output_filename, media_type='application/vnd.openxmlformats-officedocument.spreadsheet.sheet')
    except Exception as e:
        logger.error(f"Error saving or returning Excel file: {e}", exc_info=True)
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up error-generated temporary Excel file {output_filepath}: {cleanup_error}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating or returning the consolidated Excel file.")

def analyze_pdf_from_path(pdf_path: str):
    if not form_recognizer_endpoint or not form_recognizer_key:
        logger.error("Azure credentials are not set. Cannot analyze PDF.")
        return []
    if not os.path.exists(pdf_path):
        logger.error(f"Input PDF file not found at expected temporary path: {pdf_path}")
        return []
    try:
        document_client = DocumentAnalysisClient(form_recognizer_endpoint, AzureKeyCredential(form_recognizer_key))
        with open(pdf_path, "rb") as f:
            poller = document_client.begin_analyze_document(custom_model_id, f)
        logger.info(f"Polling for analysis result for {os.path.basename(pdf_path)}...")
        try:
            result = poller.result(180)
            logger.info(f"Analysis completed successfully for {os.path.basename(pdf_path)}.")
        except HttpResponseError as e:
            logger.error(f"HTTP Response Error during polling for {os.path.basename(pdf_path)}: Status Code {e.status_code}, Message: {e.message}", exc_info=True)
            if e.status_code == 429:
                logger.error(f"Rate limit hit for {os.path.basename(pdf_path)}. Please wait before sending more requests.")
            return []
        except Exception as e:
            logger.error(f"An error occurred while waiting for analysis result for {os.path.basename(pdf_path)}: {str(e)}", exc_info=True)
            return []
        if poller.status() != 'succeeded':
            logger.error(f"Analysis did not succeed for {os.path.basename(pdf_path)}. Final status: {poller.status()}")
            return []
        extracted_data = extract_table_data(result)
        if not extracted_data:
            logger.warning(f"No data extracted from {os.path.basename(pdf_path)} by extract_table_data.")
            return []
        return extracted_data
    except Exception as e:
        logger.error(f"An unexpected error occurred during analysis of {os.path.basename(pdf_path)}: {str(e)}", exc_info=True)
        return []
