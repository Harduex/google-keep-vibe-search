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

### 5. Example Usage

You can use the Vibe Search to ask questions to your notes and receive very accurate results. Here is an example of how to use the search functionality:

1. Open your browser and go to [http://127.0.0.1:8000](http://127.0.0.1:8000).
2. In the search bar, enter a query such as "meeting notes from last week" or "ideas for project".
3. Click the "Search" button.
4. The results will display matching notes sorted by relevance based on the "vibe" of your search.

For example, if you have a note with the content "Discussed project milestones in the meeting last week", and you search for "What are my meeting notes from the last week?", the Vibe Search will find and display this note as a relevant result.

Feel free to experiment with different queries to see how well the Vibe Search can find the most relevant notes based on the meaning of your search terms.

### Find Related Notes

Each note in the search results has a "Show related" button that helps you discover connections between your notes:

1. When you click the "Show related" button on a note, the system performs a new search using that note's content
2. This reveals other notes that share similar topics, ideas, or themes
3. It's a great way to rediscover forgotten notes and see connections between different ideas

## How it works

The application combines two search approaches:

1. **Semantic Search**: Uses the `sentence-transformers` model to convert your notes and queries into vector embeddings and finds similar content based on meaning.

2. **Keyword Search**: Traditional text search that looks for exact matches of words and phrases.

The results are combined with configurable weights (default: 70% semantic, 30% keyword) to give you the most relevant matches.

## Customization

You can adjust the following settings in your `.env` file:

- `SEMANTIC_SEARCH_WEIGHT`: Weight for semantic search results (0-1)
- `KEYWORD_SEARCH_WEIGHT`: Weight for keyword search results (0-1)
- `MAX_RESULTS`: Maximum number of results to return
- `HOST` and `PORT`: Server binding settings

## Troubleshooting

### No notes are being loaded

- Check that the `GOOGLE_KEEP_PATH` in your `.env` file points to the correct location
- Ensure the folder contains `.json` files from your Google Keep export

### App loads slow

- The first load might take longer as the model loads and computes embeddings
- Subsequent loads should be faster

### Missing dependencies

- Ensure you're using the virtual environment and have installed all requirements

## License

MIT License