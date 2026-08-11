from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "AI Support Bot backend is alive"}
