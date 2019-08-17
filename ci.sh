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

python -m pip install -r test-requirements.txt

#black --diff --check snekomatic

pytest -W error -r a --verbose

bash <(curl -s https://codecov.io/bash) -n "${CODECOV_NAME}"
