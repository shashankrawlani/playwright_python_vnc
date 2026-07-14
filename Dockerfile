FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for Xvfb, VNC, window manager,
# and any remaining Playwright browser deps not covered by the base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    fluxbox \
    vim \
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

# container/ holds everything that runs inside the image
COPY container/entry_point.sh .
COPY container/run_browser.sh .
COPY container/scripts/ ./scripts/
COPY .env .

# Install Playwright Python package and browser binaries
RUN pip install --no-cache-dir --break-system-packages playwright==1.61.0 \
    && playwright install \
    && playwright install-deps

# Set executable permissions
RUN chmod +x entry_point.sh run_browser.sh

# Create required directories (profiles/ is mounted at runtime via volume)
RUN mkdir -p /app/profiles /app/user_data /shared \
    && chmod -R 777 /app/profiles /app/user_data /shared

# Environment variables
ENV DISPLAY=:99
ENV USER_DATA_DIR=/app/user_data
ENV PROFILES_ROOT=/app/profiles

# VNC port — manager port 8080 is exposed by the manager service in docker-compose
EXPOSE 5900

CMD ["/app/entry_point.sh"]
