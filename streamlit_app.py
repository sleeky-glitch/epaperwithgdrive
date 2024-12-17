import streamlit as st
import fitz  # PyMuPDF
from openai import OpenAI
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import io
import base64
from PIL import Image
import time
import os
import json
import tempfile
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="ગુજરાતી સમાચાર શોધક",
    page_icon="📰",
    layout="wide",
)

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Constants
APP_FOLDER_NAME = "GujaratiNewsFinder"
CACHE_DIR = Path(tempfile.gettempdir()) / "gujarati_news_finder"
CACHE_FILE = CACHE_DIR / "processed_cache.json"
FILES_INDEX = CACHE_DIR / "files_index.json"

# Initialize session state
if 'drive_files' not in st.session_state:
    st.session_state.drive_files = {}
if 'processed_cache' not in st.session_state:
    st.session_state.processed_cache = {}
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = CACHE_DIR / "pdfs"

def setup_cache_directories():
    """Create necessary cache directories"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    st.session_state.temp_dir.mkdir(parents=True, exist_ok=True)

def load_cache():
    """Load processed results from cache file"""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache():
    """Save processed results to cache file"""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.processed_cache, f, ensure_ascii=False, indent=2)

def save_files_index():
    """Save files index to JSON"""
    with open(FILES_INDEX, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.drive_files, f, ensure_ascii=False, indent=2)

def load_files_index():
    """Load files index from JSON"""
    if FILES_INDEX.exists():
        with open(FILES_INDEX, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@st.cache_resource
def authenticate_google_drive():
    """Authenticate and connect to Google Drive"""
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    return GoogleDrive(gauth)

def get_or_create_app_folder(drive):
    """Get or create the application folder in Google Drive"""
    folders = drive.ListFile({
        'q': f"title='{APP_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    }).GetList()

    if folders:
        return folders[0]
    else:
        folder_metadata = {
            'title': APP_FOLDER_NAME,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        return folder

def sync_drive_files():
    """Sync files from Google Drive to local cache"""
    if st.session_state.drive_files:
        return  # Files already synced

    drive = authenticate_google_drive()
    app_folder = get_or_create_app_folder(drive)

    # Get all PDF files from the app folder
    file_list = drive.ListFile({
        'q': f"'{app_folder['id']}' in parents and mimeType='application/pdf' and trashed=false"
    }).GetList()

    # Download files that aren't in cache
    with st.spinner("Syncing files from Google Drive..."):
        for file in file_list:
            local_path = st.session_state.temp_dir / file['title']
            if not local_path.exists():
                file.GetContentFile(str(local_path))
            st.session_state.drive_files[file['title']] = str(local_path)

    save_files_index()
    st.success("Files synced successfully!")

# [Previous helper functions remain the same: encode_image_to_base64, convert_pdf_page_to_image, process_image_with_gpt4_vision]

def process_pdf(pdf_path, tag, progress_bar):
    """Process PDF using PyMuPDF and GPT-4 Vision"""
    try:
        # Check if results are already cached
        cache_key = f"{Path(pdf_path).name}_{tag}"
        if cache_key in st.session_state.processed_cache:
            return st.session_state.processed_cache[cache_key]

        doc = fitz.open(pdf_path)
        all_results = []
        total_pages = len(doc)

        for i, page in enumerate(doc):
            progress_bar.progress((i + 1) / total_pages,
                              f"Processing page {i + 1} of {total_pages}")

            image = convert_pdf_page_to_image(page)

            if i == 0:
                st.image(image, caption=f"Processing Page {i+1}", use_column_width=True)

            result = process_image_with_gpt4_vision(image, tag)
            if result:
                all_results.append(result)

            time.sleep(1)

        doc.close()

        # Cache the results
        final_result = "\n".join(all_results)
        st.session_state.processed_cache[cache_key] = final_result
        save_cache()

        return final_result

    except Exception as e:
        st.error(f"Error in PDF processing: {str(e)}")
        return None

def main():
    # Setup cache directories
    setup_cache_directories()

    # Load cache at startup
    st.session_state.processed_cache = load_cache()
    st.session_state.drive_files = load_files_index()

    # Sync files from Google Drive
    sync_drive_files()

    st.title("ગુજરાતી સમાચાર શોધક (Gujarati News Finder)")
    st.write("Search through Gujarati newspapers from Google Drive")

    # File selection from synced files
    st.sidebar.header("Available Files")
    selected_file = st.sidebar.selectbox(
        "Select a file to process",
        options=list(st.session_state.drive_files.keys())
    )

    # Tag input
    search_tag = st.text_input(
        "Enter search tag",
        placeholder="Enter topic in English or Gujarati",
        help="Enter the topic you want to search for in the newspapers"
    )

    # Process button
    if st.button("Search Newspapers 📰", key="process_btn"):
        if not selected_file:
            st.error("Please select a file!")
            return
        if not search_tag:
            st.error("Please enter a search tag!")
            return

        try:
            # Get the local path of the selected file
            local_path = st.session_state.drive_files[selected_file]

            st.markdown(f"### Processing file: {selected_file}")
            progress_bar = st.progress(0, f"Starting processing for {selected_file}...")

            results = process_pdf(local_path, search_tag, progress_bar)

            if results:
                st.success(f"Processing complete for {selected_file}!")
                st.markdown("### 🔍 Search Results")

                sections = results.split('---')
                for idx, section in enumerate(sections, 1):
                    if section.strip():
                        with st.container():
                            st.markdown(f"#### News Item {idx}")
                            st.markdown(section.strip())
                            st.markdown("---")
            else:
                st.error(f"No relevant news found in {selected_file}.")

        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

    # Upload new files section
    with st.expander("📤 Upload New Files"):
        st.markdown("""
        To add new files:
        1. Open your Google Drive
        2. Navigate to the 'GujaratiNewsFinder' folder
        3. Upload your PDF files there
        4. Restart the application to sync new files
        """)

    # Help section
    with st.expander("ℹ️ How to use"):
        st.markdown("""
        1. **Select File**: Choose from the available files in the sidebar
        2. **Enter Tag**: Type the topic you want to search for
        3. **Search**: Click 'Search Newspapers' button
        4. **View Results**: See original text, translation, and summary

        **Note**:
        - Files are synced from Google Drive at application startup
        - Results are cached for faster subsequent searches
        """)

if __name__ == "__main__":
    main()
