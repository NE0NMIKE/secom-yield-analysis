#!/usr/bin/env bash
# Download the SECOM dataset from the UCI Machine Learning Repository into data/.
# Safe to run repeatedly: it skips the download if the files are already there.

# Stop on any error (-e), on use of an unset variable (-u),
# and if any command in a pipeline fails (-o pipefail).
set -euo pipefail

URL="https://archive.ics.uci.edu/static/public/179/secom.zip"

# Run from the repo root (the folder this script lives in),
# so the script works no matter where it is called from.
cd "$(dirname "$0")"

DATA_DIR="data"
ZIP_PATH="$DATA_DIR/secom.zip"

mkdir -p "$DATA_DIR"

# Skip the download if both data files already exist (-f = "is a regular file").
if [[ -f "$DATA_DIR/secom.data" && -f "$DATA_DIR/secom_labels.data" ]]; then
    echo "SECOM data already present in $DATA_DIR/, skipping download."
    exit 0
fi

echo "Downloading SECOM dataset..."
# --fail: treat HTTP errors (e.g. 404) as failures rather than saving the error page.
# -L: follow redirects.  -sS: no progress bar, but still show errors.
curl --fail -sSL -o "$ZIP_PATH" "$URL"

echo "Unzipping..."
# -o: overwrite without asking.  -q: quiet.  -d: extract into this folder.
unzip -o -q "$ZIP_PATH" -d "$DATA_DIR"
rm "$ZIP_PATH"

echo "Done. Files in $DATA_DIR/:"
ls -lh "$DATA_DIR"
