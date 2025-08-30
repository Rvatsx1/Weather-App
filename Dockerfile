# Stage 1: Builder - to install dependencies and build anything needed
FROM python:3.11-slim-bookworm AS builder

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python -m venv /opt/venv
# Make sure we use the virtualenv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - the final, lean image
FROM python:3.11-slim-bookworm AS runtime

# Install runtime system dependencies (only what's needed to run, not build)
RUN apt-get update && apt-get install -y \
    libpq5 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash aura
USER aura
WORKDIR /home/aura/app

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=aura:aura /opt/venv /home/aura/venv
ENV PATH="/home/aura/venv/bin:$PATH"

# Copy application code
COPY --chown=aura:aura . .

# Expose the port Gunicorn will run on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Define the command to run the application with Gunicorn
# Bind to 0.0.0.0 to make it available outside the container
# Use 4 worker processes - adjust based on CPU cores (2-4x cores is a common rule)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app", "--timeout", "120"]