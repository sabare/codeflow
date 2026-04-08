# CodeFlow

CodeFlow is a Python + React tool for exploring Python codebases as call graphs and readable execution flows.

It scans a project, finds functions and classes, maps call relationships, and renders the result in a visual graph UI. A lightweight CLI is also included for generating JSON analysis from the terminal.

## Features

- Analyze a local Python project and build a project-level call graph.
- Inspect a single function as an expandable flow tree.
- Browse folders and Python files from the web UI.
- Render the analysis in an interactive React Flow canvas.
- Optionally generate short natural-language summaries with OpenAI.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer
- `pip`
- `npm`

## Project Structure

- `main.py` - CLI entry point that prints analysis as JSON.
- `analysis.py` - Static analysis and call graph collection.
- `flow.py` - Builds readable flow trees and optional LLM summaries.
- `backend/` - FastAPI API used by the frontend.
- `frontend/` - Vite + React application for browsing and visualizing code.

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd codeflow
```

### 2. Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install backend dependencies

The backend needs FastAPI, Uvicorn, and `python-dotenv`. If you want optional AI summaries, install `openai` too.

```bash
pip install fastapi "uvicorn[standard]" python-dotenv openai
```

If you prefer to install from the provided requirements file first, you can do that and then add the missing utilities:

```bash
pip install -r backend/requirements.txt
pip install python-dotenv openai
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

## Running the App

Open two terminals, one for the backend and one for the frontend.

### Backend

From the repository root:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

### Frontend

From the `frontend/` directory:

```bash
npm run dev
```

If you want the frontend to talk to a backend running somewhere other than `http://localhost:8000`, set `VITE_API_URL` before starting Vite:

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

## CLI Usage

You can also run the analyzer directly from the command line.

```bash
python main.py /path/to/project
```

To analyze one function and print a flow tree:

```bash
python main.py /path/to/project --function package.module.function_name
```

To limit expansion depth:

```bash
python main.py /path/to/project --function package.module.function_name --depth 2
```

## Backend API

The FastAPI backend exposes these endpoints:

- `GET /browse?path=...` - list subdirectories and Python files.
- `GET /functions?path=...` - list functions in a Python file.
- `GET /analyze?path=...` - analyze a project folder.
- `GET /analyze?path=...&function=...` - analyze a specific function and return a flow tree.

## Optional OpenAI Configuration

Function and flow summaries can use OpenAI when the following environment variables are set:

- `OPENAI_API_KEY` - required to enable LLM summaries
- `OPENAI_MODEL` - optional, defaults to `gpt-5-nano`

You can store these in a local `.env` file at the repository root.

Example:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-nano
```

If no API key is present, CodeFlow still works. It just falls back to generated summaries.

## Notes

- Analysis results may be cached in `.cache/function_summaries.json`.
- The frontend expects the backend to be running when you load a project.
- Only `.py` files are shown in the browser view.

## Contributing

Contributions are welcome. A good starting point is to:

1. Open an issue or discussion describing the change.
2. Keep edits focused and small where possible.
3. Add or update tests if you change analysis behavior.

## License

Add a license file before distributing the project publicly if one is not already present.
