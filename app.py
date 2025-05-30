from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime
import logging
from pymongo import MongoClient

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOOKINGS_FILE = 'prenotazioni.csv'
PORT = int(os.environ.get('PORT', 5000))

TIME_SLOTS = [
    "09:00-10:00",
    "10:00-11:00",
    "11:00-12:00"
]

MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    logger.error("MONGO_URI non impostata. Terminare.")
    exit(1)

mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database()
quixa_collection = db.quixa_callback


class BookingService:
    def __init__(self):
        self.init_csv_file()

    def init_csv_file(self):
        if not os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['slot_id', 'time_slot', 'user_name', 'user_email', 'booking_date', 'status'])
            logger.info("File CSV creato con intestazioni.")

    def get_available_slots(self):
        booked_slots = set()
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['status'] == 'booked':
                        booked_slots.add(int(row['slot_id']))
        except FileNotFoundError:
            pass
        return [
            {'slot_id': i, 'time_slot': slot, 'available': True}
            for i, slot in enumerate(TIME_SLOTS) if i not in booked_slots
        ]

    def get_all_slots_status(self):
        booked_slots = {}
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['status'] == 'booked':
                        booked_slots[int(row['slot_id'])] = {
                            'user_name': row['user_name'],
                            'user_email': row['user_email'],
                            'booking_date': row['booking_date']
                        }
        except FileNotFoundError:
            pass
        return [
            {
                'slot_id': i,
                'time_slot': TIME_SLOTS[i],
                'available': i not in booked_slots,
                **({'booked_by': booked_slots[i]} if i in booked_slots else {})
            } for i in range(len(TIME_SLOTS))
        ]

    def is_slot_available(self, slot_id):
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if int(row['slot_id']) == slot_id and row['status'] == 'booked':
                        return False
        except FileNotFoundError:
            pass
        return True

    def book_slot(self, slot_id, user_name, user_email):
        if slot_id < 0 or slot_id >= len(TIME_SLOTS):
            return False, "Slot ID non valido"

        if not self.is_slot_available(slot_id):
            return False, "Slot già prenotato"

        booking_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(BOOKINGS_FILE, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                slot_id,
                TIME_SLOTS[slot_id],
                user_name,
                user_email,
                booking_date,
                'booked'
            ])
        logger.info(f"Slot {slot_id} prenotato da {user_name}")

        try:
            doc = {
                "slot_id": slot_id,
                "time_slot": TIME_SLOTS[slot_id],
                "user_name": user_name,
                "user_email": user_email,
                "booking_date": booking_date,
                "status": "booked"
            }
            quixa_collection.insert_one(doc)
            logger.info(f"Prenotazione inserita in MongoDB per slot {slot_id}")
        except Exception as e:
            logger.error(f"Errore inserimento MongoDB: {e}")

        return True, "Prenotazione confermata"

    def cancel_booking(self, slot_id, user_email):
        if slot_id < 0 or slot_id >= len(TIME_SLOTS):
            return False, "Slot ID non valido"

        rows = []
        booking_found = False

        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if int(row['slot_id']) == slot_id and row['user_email'] == user_email and row['status'] == 'booked':
                        booking_found = True
                        logger.info(f"Prenotazione cancellata: Slot {slot_id}, Email {user_email}")
                    else:
                        rows.append(row)
        except FileNotFoundError:
            return False, "Nessuna prenotazione trovata"

        if not booking_found:
            return False, "Prenotazione non trovata o email non corrispondente"

        with open(BOOKINGS_FILE, 'w', newline='', encoding='utf-8') as file:
            if rows:
                fieldnames = rows[0].keys()
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            else:
                writer = csv.writer(file)
                writer.writerow(['slot_id', 'time_slot', 'user_name', 'user_email', 'booking_date', 'status'])

        try:
            result = quixa_collection.delete_one({"slot_id": slot_id, "user_email": user_email, "status": "booked"})
            if result.deleted_count > 0:
                logger.info(f"Prenotazione rimossa da MongoDB: slot {slot_id}, email {user_email}")
            else:
                logger.warning(f"Nessun documento MongoDB cancellato per slot {slot_id} e email {user_email}")
        except Exception as e:
            logger.error(f"Errore cancellazione MongoDB: {e}")

        return True, "Prenotazione cancellata"


booking_service = BookingService()

@app.route('/slots', methods=['GET'])
def get_slots():
    try:
        slots = booking_service.get_all_slots_status()
        return jsonify({'status': 'success', 'slots': slots}), 200
    except Exception as e:
        logger.error(f"Errore get_slots: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/available', methods=['GET'])
def get_available():
    try:
        available = booking_service.get_available_slots()
        return jsonify({'status': 'success', 'available_slots': available}), 200
    except Exception as e:
        logger.error(f"Errore get_available: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/convy-booking', methods=['POST'])
def convy_booking():
    try:
        data = request.get_json()
        slot_scelto = data.get('slot_scelto')
        user_name = data.get('user_name')      # se lo ricevi da Convy
        user_email = data.get('user_email')    # idem

        if slot_scelto is None or not user_name or not user_email:
            return jsonify({'error': 'slot_scelto, user_name e user_email sono obbligatori'}), 400

        if slot_scelto not in TIME_SLOTS:
            return jsonify({'error': 'slot_scelto non valido'}), 400

        slot_id = TIME_SLOTS.index(slot_scelto)

        # Costruisci il documento MongoDB
        booking_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        doc = {
            "slot_id": slot_id,
            "time_slot": slot_scelto,
            "user_name": user_name,
            "user_email": user_email,
            "booking_date": booking_date,
            "status": "booked"
        }

        # Salva in MongoDB
        quixa_collection.insert_one(doc)

        return jsonify({'status': 'success', 'message': 'Prenotazione salvata su MongoDB', 'booking': doc}), 200

    except Exception as e:
        logger.error(f"Errore convy_booking: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/cancel', methods=['POST'])
def cancel_booking():
    try:
        data = request.get_json()
        slot_id = data.get('slot_id')
        user_email = data.get('user_email')

        if slot_id is None or not user_email:
            return jsonify({'error': 'slot_id e user_email sono obbligatori'}), 400

        success, message = booking_service.cancel_booking(slot_id, user_email)

        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                'slot_id': slot_id,
                'time_slot': TIME_SLOTS[slot_id]
            }), 200
        else:
            return jsonify({'status': 'error', 'message': message}), 400

    except Exception as e:
        logger.error(f"Errore cancel_booking: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'WSCallback Booking System',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'available_slots': len(booking_service.get_available_slots())
    }), 200

@app.route('/', methods=['GET'])
def home():
    try:
        available_slots = booking_service.get_available_slots()
        return jsonify({
            'service': 'WSCallback - Sistema Prenotazioni',
            'available_slots': available_slots,
            'time_slots': TIME_SLOTS,
            'endpoints': {
                'GET /slots': 'Visualizza tutti gli slot con stato',
                'GET /available': 'Visualizza solo slot disponibili',
                'POST /book': 'Prenota uno slot (slot_id, user_name, user_email)',
                'POST /cancel': 'Cancella prenotazione (slot_id, user_email)',
                'GET /health': 'Health check del servizio'
            },
            'example_booking': {
                'url': '/book',
                'method': 'POST',
                'data': {
                    'slot_id': 0,
                    'user_name': 'Mario Rossi',
                    'user_email': 'mario@email.com'
                }
            },
            'example_cancel': {
                'url': '/cancel',
                'method': 'POST',
                'data': {
                    'slot_id': 0,
                    'user_email': 'mario@email.com'
                }
            }
        }), 200
    except Exception as e:
        logger.error(f"Errore nella home: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=== WSCallback - Sistema Prenotazioni ===")
    print("Slot disponibili:", TIME_SLOTS)
    print(f"Server in avvio su porta {PORT}")
    app.run(debug=False, host='0.0.0.0', port=PORT)
