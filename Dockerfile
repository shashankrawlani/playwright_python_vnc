FROM mcr.microsoft.com/playwright/python:v1.61.0-noble@sha256:a9731514f24121d1dcd25d58d0a38146646d290a5998fd80d3e533e7b5e21c69

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    SCREEN_RES=1280x1024x24 \
    PROFILES_ROOT=/app/profiles \
    LOCK_ROOT=/tmp/pyplayvnc-locks \
    HOME=/tmp/pyplayvnc-home \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fluxbox=1.3.7-1build2 \
       util-linux=2.39.3-9ubuntu6.5 \
       x11-utils=7.7+6build2 \
       x11vnc=0.9.16-10 \
       xvfb=2:21.1.12-1ubuntu1.6 \
    && rm -rf /var/lib/apt/lists/* \
    && usermod --login pyplayvnc --home /home/pyplayvnc --move-home --shell /usr/sbin/nologin ubuntu \
    && groupmod --new-name pyplayvnc ubuntu

WORKDIR /app

COPY manager/requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --root-user-action=ignore --no-cache-dir --break-system-packages --require-hashes -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY --chown=pyplayvnc:pyplayvnc manager/ /app/manager/
COPY --chown=pyplayvnc:pyplayvnc container/entry_point.sh container/run_browser.sh /app/
COPY --chown=pyplayvnc:pyplayvnc container/scripts/ /app/scripts/

RUN chmod 0755 /app/entry_point.sh /app/run_browser.sh /app/scripts/open_persona.py \
    && sandbox="$(find /ms-playwright -type f -path '*/chrome-linux64/chrome_sandbox' -print -quit)" \
    && test -n "$sandbox" \
    && chown root:root "$sandbox" \
    && chmod 4755 "$sandbox" \
    && mkdir -p /app/profiles /shared \
    && chown -R pyplayvnc:pyplayvnc /app /shared \
    && chmod 0700 /app/profiles /shared

USER pyplayvnc:pyplayvnc

EXPOSE 5900 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)" || exit 1

CMD ["/app/entry_point.sh"]
