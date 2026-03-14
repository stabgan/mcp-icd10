FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

# Pre-build the SQLite database at image build time for instant startup
RUN python -c "from mcp_icd10.db import get_connection; get_connection()"

ENTRYPOINT ["mcp-icd10"]
