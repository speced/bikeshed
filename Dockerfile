FROM python:3.9-bullseye as base

# Get the latest spec-data, then cache it so we don't have to redo this on every rebuild
from base as specdata
RUN mkdir /bikeshed-master
WORKDIR /bikeshed-master
RUN git clone --depth=1 --branch=master https://github.com/tabatkins/bikeshed.git /bikeshed-master
RUN pip install --editable /bikeshed-master
RUN bikeshed update

FROM base as builder
RUN mkdir /install
WORKDIR /install

COPY requirements.txt /requirements.txt
RUN pip install --prefix=/install -r /requirements.txt

FROM base
RUN mkdir -p /app/bikeshed
WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=specdata /bikeshed-master/bikeshed/spec-data /app/bikeshed/spec-data

# setup.py opens README.md, semver.txt and requirements.txt so they must be copied.
COPY setup.py README.md semver.txt requirements.txt /app/
RUN pip install --editable .

COPY .git /app/.git
COPY bikeshed.py /app/
COPY bikeshed /app/bikeshed
