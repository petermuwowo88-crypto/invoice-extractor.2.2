import streamlit as st
from main import extract_invoice_data
import pandas as pd

st.title("Invoice Extractor")

uploaded_file = st.file_uploader("Upload PDF or Image", type=["pdf", "png", "jpg"])

if uploaded_file:
    # Save temp file
    with open("temp_file", "wb") as f:
        f.write(uploaded_file.read())
    
    # Extract data
    data = extract_invoice_data("temp_file")
    
    # Show results
    st.write(pd.DataFrame([data]))
    
    # Optional: allow download as Excel
    df = pd.DataFrame([data])
    df.to_excel("output.xlsx", index=False)
    st.download_button("Download Excel", "output.xlsx")