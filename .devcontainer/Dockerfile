FROM mcr.microsoft.com/devcontainers/python:3.12

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    redis-tools \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create workspace directory
WORKDIR /workspace

# Install global Python tools
RUN pip install --upgrade pip \
    && pip install \
    black \
    flake8 \
    mypy \
    pytest \
    pytest-cov \
    pytest-asyncio \
    httpx \
    typer \
    rich

# Set Python path
ENV PYTHONPATH=/workspace/backend

# Default command
CMD ["sleep", "infinity"]
