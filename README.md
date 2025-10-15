# 🩺 AI Healthcare Symptom Checker

This is a complete AI-powered Healthcare Symptom Checker built with FastAPI, SQLModel, and Ollama. The goal of the project is to provide a locally running, privacy-friendly assistant that can analyze written symptoms and return educational information about possible health conditions. It combines a FastAPI backend connected to an Ollama model for language processing, a SQLModel-based SQLite database to store query history, and a simple responsive frontend written in HTML, CSS, and JavaScript. Everything runs locally so it can be demonstrated or extended without external services.

The application works in two parts. The backend, started with FastAPI, exposes an endpoint `/analyze` that receives text symptoms and optional user details such as age or pregnancy status. It then queries the local Ollama model (for example `gpt-oss:120b-cloud`) and structures the returned information into JSON containing probable conditions, confidence levels, explanations, and recommended next steps. Each user query is stored in a small SQLite database using SQLModel. The frontend connects to this backend through HTTP requests, presents a friendly text box to the user, animates the response as if the model is typing, and maintains a collapsible sidebar showing previous analyses. There is also a dark/light theme toggle and a clear-history button that removes all saved records.

To run everything, clone the repository from GitHub and set up a virtual environment. Use the following commands:

```bash
git clone https://github.com/<your-username>/healthcare-symptom-checker.git
cd healthcare-symptom-checker
python -m venv Env
.\Env\Scripts\activate   # or source Env/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Once dependencies are installed, start the backend server:

```bash
uvicorn backend.app:app --reload
```

The backend will listen at http://127.0.0.1:8000 and you can open http://127.0.0.1:8000/docs to view the API documentation.  
Next, open another terminal window and run the frontend using Python’s built-in server:

```bash
cd frontend
python -m http.server 5500
```

Visit http://127.0.0.1:5500 in your browser to use the web interface. Enter symptoms such as “I have a sore throat and headache” and click **Analyze Symptoms**. The AI will display several possible conditions (for example viral infection, flu, COVID-19, strep throat) with confidence bars and next-step recommendations. The app will automatically include a disclaimer reminding that it is for educational purposes only and not for diagnosis. The sidebar on the left lists all previous queries saved in the SQLite database; clicking a past entry reloads its response, and the 🧹 button clears everything. You can toggle between dark and light modes using the theme switch in the header.

The project folder looks like this:

```
healthcare-symptom-checker/
├── backend/
│   ├── app.py
│   ├── schemas.py
│   ├── __init__.py
│   └── symptom_checker.db
│
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── Env/                # virtual environment (ignored by Git)
├── requirements.txt
├── .gitignore
└── README.md
```

![Project structure](./file%20structure.jpg)

All dependencies are listed in `requirements.txt` and can be installed with `pip install -r requirements.txt`. The main libraries used are FastAPI, Uvicorn, SQLModel, SQLAlchemy, Requests, HTTPX, Python-Dotenv, PyYAML, OpenAI (optional), and Watchfiles. The app also depends on AnyIO, Sniffio, and standard Pydantic components included automatically.  

The entire system is designed to be minimal yet functional. After installation, you only need three commands to launch it:
1. `.\Env\Scripts\activate`
2. `uvicorn backend.app:app --reload`
3. `cd frontend && python -m http.server 5500`

Once both servers are running, open the browser and start interacting with the AI. The first request may take a few seconds as Ollama loads the model into memory. After that, responses appear almost instantly.

This repository already contains a demonstration video that shows the application in action. You can watch it locally by clicking the file name `Demo Video.mp4` inside the repository or replace the link below with your hosted version if you uploaded it elsewhere.

🎥 [Click to watch the demo video](./Demo%20Video.mp4)

All information produced by this system is meant purely for learning and demonstration. It does not diagnose diseases, prescribe treatment, or substitute for medical consultation. Users should always seek professional healthcare advice for real conditions.

Author: **M V K Karthikeya**  
GitHub: [[https://github.com/KarthikeyaMVK17](https://github.com/KarthikeyaMVK17)]


If you clone this repository, install the dependencies, and run both the backend and frontend as described, you’ll have a working local AI Healthcare Symptom Checker ready for presentation. The code is fully commented, uses standard FastAPI practices, and follows a simple MVC-style structure for clarity. The database can be reset by deleting the `symptom_checker.db` file, and the project automatically recreates it when restarted.

This repository contains everything required for submission, including:
- complete backend and frontend source code,
- SQLite database integration,
- dependency list,
- demonstration video,
- and this explanatory README.

It is self-contained, works entirely offline with Ollama, and can be extended with authentication, user profiles, or additional model logic.  

⭐ If you find this project useful or interesting, please give it a star on GitHub.
