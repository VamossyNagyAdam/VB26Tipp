from fastapi import FastAPI

app = FastAPI(title="VB26 Tipp")


@app.get("/")
def root():
    return {"status": "ok", "message": "VB26 Tipp backend él"}


@app.get("/health")
def health():
    return {"status": "healthy"}
