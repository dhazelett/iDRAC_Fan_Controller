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
    FAN_SPEED=5 \
    CPU_TEMPERATURE_THRESHOLD=50 \
    CHECK_INTERVAL=60 \
    DISABLE_THIRD_PARTY_PCIE_CARD_DELL_DEFAULT_COOLING_RESPONSE=false \
    KEEP_THIRD_PARTY_PCIE_CARD_COOLING_RESPONSE_STATE_ON_EXIT=false

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD [ "python", "healthcheck.py" ]

CMD ["python", "idrac_controller.py"]