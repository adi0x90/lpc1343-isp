FROM python:3.12-slim

WORKDIR /opt/lpc1343-isp
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENTRYPOINT ["lpc-isp"]
