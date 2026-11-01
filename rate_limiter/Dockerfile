FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libhiredis-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download the cpp-httplib header file (it's a header-only library, no compiling needed)
RUN wget https://raw.githubusercontent.com/yhirose/cpp-httplib/master/httplib.h -O /usr/local/include/httplib.h

WORKDIR /tmp
RUN git clone https://github.com/sewenew/redis-plus-plus.git \
    && cd redis-plus-plus \
    && mkdir build && cd build \
    && cmake -DREDIS_PLUS_PLUS_CXX_STANDARD=17 .. \
    && make -j$(nproc) \
    && make install \
    && ldconfig

WORKDIR /app
COPY . .

# Compile the server
RUN mkdir -p build && cd build && cmake .. && make

# NEW: Boot the actual C++ binary instead of sleeping
CMD ["./build/rate_limiter"]