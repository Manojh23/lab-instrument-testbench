FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY testbench ./testbench
RUN pip install --no-cache-dir '.[test]' && useradd -m tester && chown -R tester:tester /app
COPY --chown=tester:tester tests ./tests
COPY --chown=tester:tester docs ./docs
COPY --chown=tester:tester scripts ./scripts
USER tester
CMD ["bash", "scripts/check.sh"]
