# Google Keep Vibe Search

A semantic search application for your Google Keep notes export. This app lets you search through your notes using natural language queries and keywords, finding the most relevant notes based on the "vibe" of your search.

## Features

- **Semantic Search**: Find notes based on meaning, not just exact keyword matches
- **Keyword Search**: Traditional search capability for precise matching
- **Hybrid Approach**: Combines both methods for optimal results
- **Clean UI**: Simple, responsive interface inspired by Google Keep
- **Self-contained**: Easy to set up and run locally

## Requirements

- Python 3.8+
- Google Keep export from Google Takeout
- Basic understanding of command-line operations

## Setup Instructions

### 1. Export your Google Keep notes

1. Go to [Google Takeout](https://takeout.google.com/)
2. Select only "Keep" from the list of Google products
3. Click "Next step" and choose your delivery method
4. Create export and download the ZIP file
5. Extract the ZIP file to a location on your computer

### 2. Set up the Python environment

```bash
# Clone this repository or download and extract the ZIP file
git clone https://github.com/Harduex/google-keep-vibe-search.git
cd google-keep-vibe-search

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure the application

Copy the provided `.env.example` file to create a `.env` file:

```bash
# On Windows
copy .env.example .env

# On macOS/Linux
cp .env.example .env
```

Then edit the .env file to set your Google Keep export path:

```
GOOGLE_KEEP_PATH=D:\\Takeout\\Keep  # On Windows
# Or
GOOGLE_KEEP_PATH=/home/user/Downloads/Takeout/Keep  # On macOS/Linux
```

### 4. Run the application

```bash
# Make sure your virtual environment is activated
python -m app.main
```

The application should now be running at http://127.0.0.1:8000

### 5. Using the application

1. Open your browser and go to http://127.0.0.1:8000
2. Use the search bar to enter your queries
3. Results will display matching notes sorted by relevance

## How it works

The application combines two search approaches:

1. **Semantic Search**: Uses the `sentence-transformers` model to convert your notes and queries into vector embeddings and finds similar content based on meaning.

2. **Keyword Search**: Traditional text search that looks for exact matches of words and phrases.

The results are combined with configurable weights (default: 70% semantic, 30% keyword) to give you the most relevant matches.

## Customization

You can adjust the following settings in `app/config.py`:

- `SEMANTIC_SEARCH_WEIGHT`: Weight for semantic search results (0-1)
- `KEYWORD_SEARCH_WEIGHT`: Weight for keyword search results (0-1)
- `MAX_RESULTS`: Maximum number of results to return
- `HOST` and `PORT`: Server binding settings

## Troubleshooting

### No notes are being loaded

- Check that the `GOOGLE_KEEP_PATH` in `config.py` points to the correct location
- Ensure the folder contains `.json` files from your Google Keep export

### Search is slow

- The first search might take longer as the model loads and computes embeddings
- Subsequent searches should be faster

### Missing dependencies

- Ensure you're using the virtual environment and have installed all requirements

## License

MIT License