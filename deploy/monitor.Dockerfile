FROM docker.arvancloud.ir/python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY dashboard ./dashboard
USER 10001:10001
EXPOSE 3000
CMD ["python", "-m", "dashboard.cloud"]
