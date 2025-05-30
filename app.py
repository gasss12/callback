import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Setup MongoDB
mongo_uri = os.environ.get("MONGO_URI")
client = MongoClient(mongo_uri)
db = client["quixa"]
collection = db["quixa_collection"]  # <-- Collection aggiornata

# Time slots disponibili
time_slots = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00", "17:30", "18:00", "18:30"
]

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    user_id = data.get("user_id")
    giorno = data.get("giorno")
    orario = data.get("orario")

    if not user_id or not giorno or not orario:
        return jsonify({"success": False, "message": "Dati mancanti"}), 400

    if orario not in time_slots:
        return jsonify({"success": False, "message": "Orario non valido"}), 400

    # Verifica se l'orario è già prenotato
    if collection.find_one({"giorno": giorno, "orario": orario}):
        return jsonify({"success": False, "message": "Orario già prenotato"}), 409

    # Salva la prenotazione nel database
    collection.insert_one({
        "user_id": user_id,
        "giorno": giorno,
        "orario": orario
    })

    return jsonify({"success": True, "message": "Prenotazione registrata"}), 200

@app.route("/prenotazioni", methods=["GET"])
def get_prenotazioni():
    giorno = request.args.get("giorno")
    if not giorno:
        return jsonify({"success": False, "message": "Parametro 'giorno' mancante"}), 400

    prenotazioni = list(collection.find({"giorno": giorno}, {"_id": 0}))
    return jsonify(prenotazioni), 200

if __name__ == "__main__":
    app.run(debug=True)
