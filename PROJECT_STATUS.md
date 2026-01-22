# Project Status & Handover

**Last Updated:** 2026-01-21
**Project:** Product Image Sourcer (Web & Script)

## Overview
This project is an automated product image sourcing tool that scrapes images from DuckDuckGo (primary) and Bing (fallback) based on a product list. It validates images using fuzzy matching (80% threshold) against the product name.

It includes both a command-line script (`image_sourcer.py`) and a modern Flask-based web interface (`app.py`).

## File Structure
- `app.py`: Flask backend for the web interface.
- `image_sourcer.py`: Core logic module. Contains `process_items` generator and multi-engine search logic.
- `templates/index.html`: Main frontend HTML.
- `static/style.css`: Premium dark-mode styling.
- `static/script.js`: Frontend logic (Drag & Drop, SSE, Animations).
- `input.csv`: Default input file for CLI usage.
- `image_sourcing_log.csv`: Audit log of processed items (SKU, Score, URL).
- `product_images/`: Directory where downloaded images are saved.

## Usage

### Web Interface (Recommended)
1. Run `python app.py`
2. Open `http://localhost:5000`
3. Drag & drop a CSV or Excel file.
   - Required columns: `SKU`, `Name` (case-insensitive).
4. Click "Start Sourcing".

### Command Line
1. Update `input.csv` with your products.
2. Run `python image_sourcer.py`
   - Use `--dry-run` to process only the first 5 items.

## Key Features
- **Multi-Engine**: Automatically switches to Bing if DuckDuckGo fails (e.g., 403 Rate Limit).
- **Anti-Blocking**: Randomized User-Agents, variable delays between requests.
- **State Management**: Resumes from `image_sourcing_log.csv` to avoid re-processing SKUs.
- **Fuzzy Validation**: Extracts image titles and requires an 80% Partial Ratio match.

## Detailed Status
- **Backend**: 
    - Implements **3-Stage Retry Logic**: (1) DDG Standard, (2) Bing Fallback, (3) DDG Broad Match.
    - Yields real-time statuses: "Searching", "Downloading", "Success", "Failed".
- **Frontend**: 
    - **Stop Button**: Allows canceling the process at any time.
    - **Loading Spinner**: Visual feedback during "Searching" and "Downloading" states.
- **Known Issues**: 
    - DuckDuckGo currently returns 403 Rate Limits frequently. The script handles this by failing over to Bing.
    - Searching is slow intentionally (delays added) to prevent IP bans.

- **Recent Changes**:
    - [x] Implemented Drag & Drop Web UI with Flask.
    - [x] Added Bing search scraper as fallback engine.
    - [x] Added resume capability and audit logging.
    - [x] Added Stop button and Loading Spinner.
