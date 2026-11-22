# syntax=docker/dockerfile:1

FROM python:3.14-alpine3.23

ENV PYCURL_SSL_LIBRARY=openssl

RUN apk add --no-cache \
        ca-certificates \
        crc32c \
        ffmpeg \
        libcurl \
        libstdc++ \
        tzdata

WORKDIR /app

COPY requirements.txt requirements.txt

# pycurl and google-crc32c have no musllinux wheels; build them against
# Alpine's libcurl/crc32c, then remove the compiler packages from this layer.
RUN apk add --no-cache --virtual .build-deps \
        build-base \
        crc32c-dev \
        curl-dev \
        openssl-dev \
    && pip3 install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

COPY *.py ./
COPY streamonitor ./streamonitor

EXPOSE 5000
CMD [ "python3", "Downloader.py"]
