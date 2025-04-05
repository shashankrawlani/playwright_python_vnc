FROM mcr.microsoft.com/playwright/python:v1.51.0-noble

ENV DEBIAN_FRONTEND=noninteractive

# Install additional system dependencies for Xvfb, VNC, and window manager
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    fluxbox \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install optional dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxrandr2 \
    libxdamage1 \
    libxkbcommon-x11-0 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY entry_point.sh .

RUN pip install playwright==1.51.0

# Ensure Playwright and its dependencies are installed
RUN playwright install && playwright install-deps

# Set executable permissions
RUN chmod +x entry_point.sh

# Ensure directories are writable
RUN mkdir -p /app/user_data/
RUN mkdir -p /app/user_data/
RUN mkdir -p /shared
RUN chmod -R 777 /app/user_data
RUN mkdir -p /shared

# Environment variables
ENV DISPLAY=:99
ENV USER_DATA_DIR=/app/user_data

# Expose ports
EXPOSE 5900

# Default command
CMD ["/app/entry_point.sh"]