FROM python:3.12-alpine

LABEL org.opencontainers.image.authors="dhazelett"

RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    ipmitool

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV IDRAC_HOST=local \
    IDRAC_USERNAME=root \
    IDRAC_PASSWORD=calvin \
    FAN_SPEED=25 \
    FAN_SPEED_MAX=100 \
    CPU_TEMPERATURE_THRESHOLD=60 \
    CHECK_INTERVAL=15 \
    DISABLE_THIRD_PARTY_PCIE_CARD_DELL_DEFAULT_COOLING_RESPONSE=false \
    KEEP_THIRD_PARTY_PCIE_CARD_COOLING_RESPONSE_STATE_ON_EXIT=false \
    FAN_RPM_MIN=2500 \
    FAN_RPM_MAX=12000 \
    CALIBRATE_FANS=false \
    ENABLE_DEBUG_OUTPUT=false \
    ENABLE_DYNAMIC_UPDATES=true \
    JUNCTION_OFFSET=15

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD [ "python", "healthcheck.py" ]

CMD ["python", "pydrac.py"]