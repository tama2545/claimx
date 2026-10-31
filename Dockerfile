FROM python:3.9-slim

ENV DEBIAN_FRONTEND=noninteractive

# =====================================================
# System packages
# =====================================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    wget \
    unzip \
    xvfb \
    dumb-init \
    ca-certificates \
    gnupg \
    fonts-liberation \
    fonts-noto-color-emoji \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libu2f-udev \
    libvulkan1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    tor \
    netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

# =====================================================
# Google Chrome
# =====================================================
RUN mkdir -p /etc/apt/keyrings && \
    wget -qO- https://dl.google.com/linux/linux_signing_key.pub | \
    gpg --dearmor > /etc/apt/keyrings/google.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# =====================================================
# NodeJS
# =====================================================
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# =====================================================
# ENV
# =====================================================
ENV DISPLAY=:99 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROME_PATH=/usr/bin/google-chrome \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

# =====================================================
# Copy files
# =====================================================
COPY . .

# =====================================================
# Extract Api
# =====================================================
RUN unzip Api.zip && rm Api.zip

# =====================================================
# Python
# =====================================================
RUN python -m pip install --upgrade pip

RUN python -m pip install --no-cache-dir \
    stem \
    requests \
    beautifulsoup4 \
    colorama \
    flask \
    playwright

RUN if [ -f requirements.txt ]; then \
    python -m pip install --no-cache-dir -r requirements.txt; \
    fi

# =====================================================
# Node
# =====================================================
WORKDIR /app/Api

RUN npm install --omit=dev

RUN npm install \
    generic-pool \
    p-queue@7 \
    jimp \
    tesseract.js \
    playwright

WORKDIR /app

# =====================================================
# Permission
# =====================================================
RUN chmod +x /app/entrypoints.sh

# =====================================================
# Debug
# =====================================================
RUN echo "===== PYTHON =====" && \
    python --version && \
    which python && \
    python -c "import stem; print('Stem OK:', stem.__version__)" && \
    python -c "import playwright; print('Python Playwright OK')" && \
    echo "===== CHROME =====" && \
    ls -lh /usr/bin/google-chrome && \
    /usr/bin/google-chrome --version

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
CMD curl -fs http://127.0.0.1:8080 || exit 1

EXPOSE 8080

ENTRYPOINT ["dumb-init","--"]

CMD ["/app/entrypoints.sh"]
