from flask import Flask, request, send_file
import pandas as pd
from io import BytesIO

app = Flask(__name__)

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NISSI FULFILLMENT</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 40px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            h1 {
                color: #333;
                text-align: center;
            }
            .upload-section {
                background-color: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                margin-bottom: 20px;
            }
            input[type="file"] {
                display: block;
                margin: 10px 0;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                width: 100%;
                box-sizing: border-box;
            }
            button {
                background-color: #4CAF50;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
                display: block;
                margin: 10px auto;
            }
            button:hover {
                background-color: #45a049;
            }
            .progress {
                display: none;
                text-align: center;
                color: #333;
                font-weight: bold;
                margin-top: 10px;
            }
            .instructions {
                font-size: 14px;
                color: #666;
                margin-bottom: 20px;
                text-align: center;
            }
        </style>
    </head>
    <body>
        <h1>NISSI FULFILLMENT</h1>
        <div class="instructions">
            Upload up to 30 Excel files with a "Carton ID" and "Scan Count" column. The files will be combined, sorted by Carton ID, and the "Scan Count" column will be set to 0.
        </div>
        <div class="upload-section">
            <input type="file" id="files" multiple accept=".xlsx,.xls" />
            <button onclick="uploadFiles()">Upload and Consolidate</button>
        </div>
        <div id="progress" class="progress">Processing your files, please wait...</div>
        <script>
            async function uploadFiles() {
                const files = document.getElementById('files').files;
                if (files.length === 0) {
                    alert('Please select at least one Excel file.');
                    return;
                }
                if (files.length > 30) {
                    alert('Please select no more than 30 Excel files.');
                    return;
                }
                const formData = new FormData();
                for (let file of files) {
                    formData.append('files', file);
                }
                document.getElementById('progress').style.display = 'block';
                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });
                    if (response.ok) {
                        const blob = await response.blob();
                        const link = document.createElement('a');
                        link.href = window.URL.createObjectURL(blob);
                        link.download = 'DATABASE_INTL_TICKETING.xlsx';
                        document.body.appendChild(link);
                        link.click();
                        link.remove();
                        window.URL.revokeObjectURL(link.href);
                        alert('Files processed successfully! The consolidated file has been downloaded.');
                    } else {
                        const errorText = await response.text();
                        alert('Error processing files: ' + errorText);
                    }
                } catch (error) {
                    alert('Error: ' + error.message);
                }
                document.getElementById('progress').style.display = 'none';
            }
        </script>
    </body>
    </html>
    '''

@app.route('/upload', methods=['POST'])
def upload():
    files = request.files.getlist('files')
    if not files or len(files) > 30:
        print("Validation failed: Please upload 1 to 30 Excel files.")
        return 'Please upload 1 to 30 Excel files.', 400

    dfs = []
    for file in files:
        try:
            print(f"Reading file: {file.filename}")
            df = pd.read_excel(file, dtype=str)  # Read all columns as strings
            # Normalize column names for internal processing
            df.columns = df.columns.str.strip().str.lower()
            print(f"Normalized columns in {file.filename}: {list(df.columns)}")
            
            # Check for required columns
            if 'carton id' not in df.columns:
                print(f"Missing 'Carton ID' in {file.filename}")
                return f'Error: File {file.filename} is missing "Carton ID" column.', 400
            if 'scan count' not in df.columns:
                print(f"Missing 'Scan Count' in {file.filename}")
                return f'Error: File {file.filename} is missing "Scan Count" column.', 400
            
            # Restore original column names for output
            original_columns = ['Carton ID', 'BARCODE', 'ARTICLE', 'PRICE', 'QUANTITY', 'Scan Count']
            if len(df.columns) != len(original_columns):
                print(f"Column count mismatch in {file.filename}: expected {len(original_columns)}, got {len(df.columns)}")
                return f'Error: File {file.filename} must have exactly 6 columns matching the input format.', 400
            df.columns = original_columns
            
            dfs.append(df)
        except Exception as e:
            print(f"Error reading file {file.filename}: {str(e)}")
            return f'Error reading file {file.filename}: {str(e)}', 400

    # Consolidate all dataframes
    try:
        print("Consolidating dataframes...")
        consolidated_df = pd.concat(dfs, ignore_index=True)
        print(f"Consolidated dataframe columns: {list(consolidated_df.columns)}")
        
        # Sort by Carton ID
        consolidated_df.sort_values(by='Carton ID', inplace=True)
        
        # Set the Scan Count column to 0
        if 'Scan Count' in consolidated_df.columns:
            consolidated_df['Scan Count'] = 0
        else:
            print("Missing 'Scan Count' after consolidation")
            return 'Error: "Scan Count" column missing after consolidation.', 400

        # Create a new Excel workbook
        print("Creating Excel output...")
        output = BytesIO()
        
        # Write the dataframe starting from row 1 (headers on row 1, data from row 2)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            consolidated_df.to_excel(writer, sheet_name='Sheet1', startrow=0, index=False)

        output.seek(0)
        print("Excel output created successfully.")
    except Exception as e:
        print(f"Error processing files: {str(e)}")
        return f'Error processing files: {str(e)}', 500

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='DATABASE_INTL_TICKETING.xlsx'
    )

if __name__ == '__main__':
    app.run(debug=True)
