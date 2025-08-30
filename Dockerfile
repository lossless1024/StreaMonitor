# syntax=docker/dockerfile:1

FROM python:3.12-alpine3.19

ENV PYCURL_SSL_LIBRARY=openssl

# Install dependencies
RUN apk add --no-cache ffmpeg libcurl

WORKDIR /app

RUN apk add --no-cache --virtual .build-dependencies build-base curl-dev \
    && pip install pycurl \
    && apk del .build-dependencies

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY *.py ./
COPY streamonitor ./streamonitor

EXPOSE 5000
CMD [ "python3", "Downloader.py"]

