# Metadata Evaluation

This folder contains the standalone metadata evaluation script.

## Requirements

- Python 3.11 or newer
- The Python packages listed in `requirements.txt`

## Setup

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate the environment.

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

The evaluator requires:

- a metadata file (ISO XML or DCAT XML)
- the corresponding dataset file (GeoJSON)

Run:

```bash
python evaluate_metadata.py --metadata <path-to-metadata-file> --data <path-to-dataset-file>
```

Example:

```bash
python evaluate_metadata.py \
  --metadata metadata.xml \
  --data dataset.geojson
```

The script automatically detects whether the metadata file is ISO or DCAT and prints the metadata evaluation result.
