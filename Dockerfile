FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    git \
    wget \
    gcc \
    libc6-dev \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/esp/tools
WORKDIR /opt/esp/tools

RUN wget -q https://github.com/espressif/binutils-gdb/releases/download/esp-gdb-v16.3_20250913/xtensa-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz && \
    tar -xzf xtensa-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz && \
    rm xtensa-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz

RUN wget -q https://github.com/espressif/binutils-gdb/releases/download/esp-gdb-v16.3_20250913/riscv32-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz && \
    tar -xzf riscv32-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz && \
    rm riscv32-esp-elf-gdb-16.3_20250913-aarch64-linux-gnu.tar.gz

ENV PATH="/opt/esp/tools/xtensa-esp-elf-gdb/bin:/opt/esp/tools/riscv32-esp-elf-gdb/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m grpc_tools.protoc -I=. --python_out=. telemetry.proto

EXPOSE 8000

CMD ["sh", "-c", "sleep 5 && uvicorn main:app --host 0.0.0.0 --port 8000"]
