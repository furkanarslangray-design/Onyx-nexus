FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# CrewAI, LangGraph, ve network tools
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "crewai/swarm_orchestrator.py"]
