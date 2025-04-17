import glob
import os
from docx_processor import WordProcessor
import pandas as pd
from parse_xml import check_consent_from_docx, check_proxima_visita_checkbox
import io
import requests
import io
from PIL import Image

def process_docx_file(docx_file):
    """
    Process a single .docx file and return a DataFrame with all the extracted information.
    
    Args:
        docx_file (str or io.BytesIO): Path to the .docx file to process or file-like object
        
    Returns:
        pandas.DataFrame: DataFrame containing all processed data from the document
    """
    # Check if input is a file path or a file-like object
    if isinstance(docx_file, str):
        with open(docx_file, "rb") as f:
            doc = WordProcessor(f)
        # Get consent status
        perdida_c_vida = check_consent_from_docx(docx_file)
        proxima_visita = check_proxima_visita_checkbox(docx_file)
        # Get filename until first space
        doc_number = os.path.basename(docx_file).split(" ")[0]
    else:
        # Assume it's a file-like object (BytesIO)
        docx_file.seek(0)
        doc = WordProcessor(docx_file)
        
        # Create new BytesIO objects for XML processing
        docx_file.seek(0)
        docx_file_xml = io.BytesIO(docx_file.getvalue())
        perdida_c_vida = check_consent_from_docx(docx_file_xml)
        
        docx_file.seek(0)
        docx_file_xml = io.BytesIO(docx_file.getvalue())
        proxima_visita = check_proxima_visita_checkbox(docx_file_xml)
        
        # Get filename from the name attribute if available
        if hasattr(docx_file, 'name'):
            doc_number = os.path.basename(docx_file.name).split(" ")[0]
        else:
            doc_number = "Unknown"
    
    # Combine the base data from doc.df with each visit row
    visits = [doc.first_medical_visit] + doc.next_medical_visits
    combined_visits = []
    
    for visit, proxima in zip(visits, proxima_visita):
        if visit is not None and not visit.empty:
            combined = pd.concat([doc.df.reset_index(drop=True), visit.reset_index(drop=True)], axis=1)
            # Add the perdida_c_vida column and doc name
            combined['Pérdida c vida'] = perdida_c_vida
            combined['Proxima visita'] = proxima
            combined['Numero de documento'] = doc_number
            combined_visits.append(combined)
    
    # Remove duplicate column labels from each DataFrame
    cleaned = [df.loc[:, ~df.columns.duplicated()] for df in combined_visits]
    
    if not cleaned:
        return pd.DataFrame()  # Return empty DataFrame if no data was processed
    
    # Get the union of all columns across all combined DataFrames
    all_columns = pd.Index([])
    for df in cleaned:
        all_columns = all_columns.union(df.columns)
    
    # Reindex each DataFrame to have the full set of columns
    final_list = [df.reindex(columns=all_columns) for df in cleaned]
    
    # Concatenate all rows into a single DataFrame
    final_df = pd.concat(final_list, ignore_index=True)
    
    ## NEW CODE ##
    # Repeat columns
    # Copy 'Antecedentes médicos del lesionado' from the first row to all other rows
    if 'Antecedentes médicos del lesionado' in final_df.columns and len(final_df) > 1:
        # Get the value from the first row
        antecedentes_value = final_df['Antecedentes médicos del lesionado'].iloc[0]
        # Copy to all other rows
        final_df.loc[1:, 'Antecedentes médicos del lesionado'] = antecedentes_value
        
    # Copy 'Descripción del accidente' from the first row to all other rows
    if 'Descripción del accidente' in final_df.columns and len(final_df) > 1:
        # Get the value from the first row
        descripcion_accidente_value = final_df['Descripción del accidente'].iloc[0]
        # Copy to all other rows
        final_df.loc[1:, 'Descripción del accidente'] = descripcion_accidente_value
        
    # Copy 'Relación de causalidad' from the first row to all other rows
    if 'Relación de causalidad' in final_df.columns and len(final_df) > 1:
        # Get the value from the first row
        causalidad_value = final_df['Relación de causalidad'].iloc[0]
        # Copy to all other rows
        final_df.loc[1:, 'Relación de causalidad'] = causalidad_value
    ## END NEW CODE ##
    
    ## NEW CODE ##
    # Remove all alpha characters from 'Fecha visita'
    if 'Fecha visita' in final_df.columns:
        # Use regex to keep only non-alpha characters (digits, punctuation, spaces)
        final_df['Fecha visita'] = final_df['Fecha visita'].astype(str).str.replace(r'[a-zA-Z]', '', regex=True)
        # Clean up any extra spaces that might result
        final_df['Fecha visita'] = final_df['Fecha visita'].str.strip()
    ## END NEW CODE ##
    
    ## NEW CODE ##
    # Unify 'Fecha visita' and 'Fecha de consulta extra' columns
    if 'Fecha de consulta extra' in final_df.columns and 'Fecha visita' in final_df.columns:
        # Where 'Fecha de consulta extra' has values, copy them to 'Fecha visita'
        mask = final_df['Fecha de consulta extra'].notna()
        final_df.loc[mask, 'Fecha visita'] = final_df.loc[mask, 'Fecha de consulta extra']
        
        # Remove the 'Fecha de consulta extra' column
        final_df = final_df.drop(columns=['Fecha de consulta extra'])
    ## END NEW CODE ##
    
    # Reorder columns: first the base columns from doc.df
    base_cols = list(cleaned[0].columns)
    visit_cols_order = [col for col in final_df.columns if col not in base_cols]
    final_order = base_cols + visit_cols_order
    final_df = final_df.reindex(columns=final_order)
    
    return final_df


def get_image_from_gdrive(gdrive_url: str) -> io.BytesIO:
    """
    Downloads an image from a Google Drive shared URL and returns it as a BytesIO object.

    Args:
        gdrive_url (str): The shared Google Drive URL (must be publicly accessible).

    Returns:
        io.BytesIO: The image in memory as a file-like object.
    
    Raises:
        ValueError: If the file ID cannot be extracted or the download fails.
    """
    try:
        # Extract file ID
        if "/file/d/" in gdrive_url:
            file_id = gdrive_url.split("/file/d/")[1].split("/")[0]
        else:
            raise ValueError("Invalid Google Drive URL format.")

        # Build direct download URL
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        # Attempt to download the file
        response = requests.get(download_url)
        if response.status_code != 200:
            raise ValueError("Failed to download image from Google Drive.")

        # Return as BytesIO (like st.file_uploader)
        image_bytes = io.BytesIO(response.content)
        return image_bytes
    except Exception as e: # catch other errors
        print(f"An unexpected error occurred: {e}")
        return None
