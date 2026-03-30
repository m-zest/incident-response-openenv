"""OpenEnv server entry point."""
from incident_response_env.server.app import app

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()
