#!/bin/bash

VENV_DIR=".venv"
PYTHON_BIN="python3"
INSTALL_NEEDED=0

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR"
    $PYTHON_BIN -m venv "$VENV_DIR"
    INSTALL_NEEDED=1
else
    echo "Reusing existing virtual environment in $VENV_DIR"
fi

if [ "$0" = "$BASH_SOURCE" ]; then
    echo "You must source this script to activate the virtual environment:"
    echo "    source $0"
    exit 1
fi

source "$VENV_DIR/bin/activate"
echo "Virtual environment activated: $VIRTUAL_ENV"

if [ "$INSTALL_NEEDED" = "1" ]; then
    echo "Installing package in editable mode..."
    pip install --upgrade pip
    pip install -e .
    echo "Installation complete."
fi
