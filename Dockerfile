# --- Build recipe for Context Exchange API ---
# Railway (or any Docker host) reads this to build and run the app.

# Start with a slim Python 3.12 image (small + fast to build)
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy just the project config first (so dependency install gets cached
# and doesn't re-run unless dependencies actually change)
COPY pyproject.toml .

# Install the project dependencies
RUN pip install --no-cache-dir .

# Now copy the actual application code
COPY src/ src/

# Install the project itself (editable not needed in prod)
RUN pip install --no-cache-dir .

# Railway sets PORT env var — default to 8000 if not set
ENV PORT=8000

# Run the server — listens on all interfaces so Railway can route to it
# Uses $PORT so Railway can control which port to bind
CMD ["sh", "-c", "uvicorn src.app.main:app --host 0.0.0.0 --port $PORT"]
