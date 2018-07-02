#!/bin/bash

set -e

for DIRECTORY in "htmlcov" "htmlcov-coverage-dj18-authentic-pg" "htmlcov-coverage-dj18-rbac-pg" "venv"
do
    if [ -d "$DIRECTORY" ]; then
        rm -r $DIRECTORY
    fi
done

virtualenv venv
venv/bin/pip install tox
venv/bin/tox -rv
