# Obsidian Corvids 🐦‍⬛
### Virtual C-Suite Executive Hub

Python-based multi-agent executive running localy built with Streamlit and Ollama.
This project uses multi-agent orchestration and dynamic tool-routing across critical enterprise domains.

The project draft split roles in: CFO, CISO, CMO, and COO using local models with zero external API dependencies.

Designed as an experimental architecture for mini enterprise workflows:
- It route natural language queries to specialized functional tools.
- Maintain conversation state and share executive-level insights in real time.

---

### How to Run Locally - First-Time Setup
If this is your first time cloning or running the repository on your machine, follow these steps in your terminal:

1. **Create and activate a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Ensure Ollama is running and download the model:**
   Make sure your local Ollama desktop app or service is active, then pull the required model:
   ```powershell
   ollama pull llama3.2
   ```

4. **Launch the application:**
   ```powershell
   python -m streamlit run app.py
   ```

#### Subsequent Executions
Once you have already set up the project and environment, running it day-to-day only takes two quick steps:

1. **Activate the virtual environment:**
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. **Launch the application:**
   ```powershell
   python -m streamlit run app.py
