# BASE IMAGE
# Sử dụng Python 3.9 slim để giảm kích thước image (codebase không dùng GPU)
FROM python:3.9-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# SYSTEM DEPENDENCIES
# Cài đặt các gói hệ thống cần thiết
RUN apt-get update && apt-get install -y \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# PROJECT SETUP
# Thiết lập thư mục làm việc
WORKDIR /code

# INSTALL LIBRARIES (OPTIMIZE: Copy requirements first for better caching)
# Copy requirements.txt trước để cache layer install libraries
COPY requirements.txt /code/

# Nâng cấp pip và cài đặt các thư viện từ requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Download spacy model (cache this layer)
RUN python3 -m spacy download vi_core_news_lg || true

# Copy source code AFTER installing dependencies
# Khi chỉ sửa code, layer này rebuild nhưng không phải reinstall libraries
COPY . /code

# EXECUTION
# Lệnh chạy mặc định khi container khởi động
# Pipeline sẽ đọc private_test.json và xuất ra submission.csv, submission_time.csv
CMD ["bash", "inference.sh"]
