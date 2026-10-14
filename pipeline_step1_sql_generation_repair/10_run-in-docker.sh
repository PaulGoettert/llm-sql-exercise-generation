
echo "Starte 10_run-in-docker.sh"
echo "aktuelles Verzeichnis:"
pwd
echo "Inhalt:"
ls

# 1) Lokale Ollama-Installation in den PATH hängen
echo "füge ${PROJECT_ROOT:-/public}/ollama/ollama-local zum PATH hinzu..."
export PATH="${PROJECT_ROOT:-/public}/ollama/ollama-local/bin:$PATH"

echo "welche ollama wird verwendet?"
which ollama || echo "ollama nicht im PATH!"

echo "ollama version:"
ollama --version

# 2) Ollama-Server starten
echo "ollama serve starten..."
ollama serve &

echo "warte, bis ollama läuft..."
sleep 20

# 3) Modell aus deinem Modelfile bauen
echo "ollama create:"
ollama create Arctic-Text2SQL-R1-7B.f16 -f ${MODELFILE_PATH:-${PROJECT_ROOT:-/public}/ollama/Modelfile3}

echo "ollama list:"
ollama list

# 4) Python-Umgebung
echo "pip install sqlglot (falls noch nicht installiert)..."
pip install -q sqlglot








#echo "ls: "



#ls

#echo "ollama starten"
#ollama serve &

#echo "so eeeepy"
#sleep 10

#echo "ollama create: "
#ollama create gpt-oss-20b -f ollama/Modelfile2

#liste alle lama modelle auf
#echo "ollama list: "
#ollama list

#for some reason didnt work in dockerfile image \_(-_-)_/
#echo "pip install: "
#pip install sqlglot

echo "python code: "

python3 code/01_model1.py 1 1
python3 code/01_model1.py 1 2
python3 code/01_model1.py 1 3
python3 code/01_model1.py 1 4
python3 code/01_model1.py 2 1
python3 code/01_model1.py 2 2
python3 code/01_model1.py 2 3
python3 code/01_model1.py 2 4
python3 code/01_model1.py 3 1
python3 code/01_model1.py 3 2
python3 code/01_model1.py 3 3
python3 code/01_model1.py 3 4
python3 code/01_model1.py 4 1
python3 code/01_model1.py 4 2
python3 code/01_model1.py 4 3
python3 code/01_model1.py 4 4
python3 code/01_model1.py 5 1
python3 code/01_model1.py 5 2
python3 code/01_model1.py 5 3
python3 code/01_model1.py 5 4
python3 code/01_model1.py 6 1
python3 code/01_model1.py 6 2
python3 code/01_model1.py 6 3
python3 code/01_model1.py 6 4
python3 code/01_model1.py 7 1
python3 code/01_model1.py 7 2
python3 code/01_model1.py 7 3
python3 code/01_model1.py 7 4
python3 code/01_model1.py 8 1
python3 code/01_model1.py 8 2
python3 code/01_model1.py 8 3
python3 code/01_model1.py 8 4
