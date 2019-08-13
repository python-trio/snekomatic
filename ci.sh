#!/bin/bash

set -ex -o pipefail

# Log some general info about the environment
env | sort

if [ "$SYSTEM_JOBIDENTIFIER" != "" ]; then
    # azure pipelines
    CODECOV_NAME="$SYSTEM_JOBIDENTIFIER"
else
    CODECOV_NAME="${TRAVIS_OS_NAME}-${TRAVIS_PYTHON_VERSION:-unknown}"
fi

python -c "import sys, struct, ssl; print('#' * 70); print('python:', sys.version); print('version_info:', sys.version_info); print('bits:', struct.calcsize('P') * 8); print('openssl:', ssl.OPENSSL_VERSION, ssl.OPENSSL_VERSION_INFO); print('#' * 70)"

python -m pip install -U pip setuptools wheel
python -m pip --version

if [ "$CHECK_FORMATTING" = "1" ]; then
    python -m pip install -r dev-requirements.txt
    black --diff --check snekbot
else
    pip install -r requirements.txt
    pytest -W error -r a --cov="snekbot" --cov-config=.coveragerc --verbose

    bash <(curl -s https://codecov.io/bash) -n "${CODECOV_NAME}"
fi
