from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "API Service Running"}

@app.get("/hello")
def read_root():
    return {"message": "hello"}
