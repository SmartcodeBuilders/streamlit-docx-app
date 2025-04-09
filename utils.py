import glob
import os
from docx_processor import WordProcessor
import pandas as pd
from parse_xml import check_consent_from_docx, check_proxima_visita_checkbox
import io

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
    
    # Reorder columns: first the base columns from doc.df
    base_cols = list(cleaned[0].columns)
    visit_cols_order = [col for col in final_df.columns if col not in base_cols]
    final_order = base_cols + visit_cols_order
    final_df = final_df.reindex(columns=final_order)
    
    return final_df
