FROM python:2.7-jessie as base

FROM base as builder
RUN mkdir /install
WORKDIR /install

COPY requirements.txt /requirements.txt
RUN pip install --install-option="--prefix=/install" -r /requirements.txt

FROM base
COPY --from=builder /install /usr/local
COPY . /app
WORKDIR /app
RUN pip install --editable .
RUN bikeshed update
