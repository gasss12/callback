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
    "10:00",
    "11:00",
    "12:00"
]

MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    logger.error("MONGO_URI non impostata. Terminare.")
    exit(1)

mongo_client = MongoClient(MONGO_URI)
db = mongo_client['quixa']
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

# SOSTITUISCI IL TUO ENDPOINT /convy-booking CON QUESTO:
@app.route('/available-mongo', methods=['GET'])
def available_slots():
    try:
        # Lista completa degli slot orari disponibili
        all_slots = ["10:00", "11:00", "12:00"]

        # Recupera i time_slot già prenotati dal DB (status = booked)
        booked = quixa_collection.find(
            {'status': 'booked'},
            {'time_slot': 1, '_id': 0}
        )
        booked_slots = [b['time_slot'] for b in booked]

        # Filtra solo gli slot ancora disponibili
        available_slots = [slot for slot in all_slots if slot not in booked_slots]

        return jsonify({'available_slots': available_slots}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/convy-booking', methods=['POST'])
def convy_booking():
    try:
        # Log di tutto quello che arriva
        logger.info("="*50)
        logger.info("🔍 NUOVA RICHIESTA /convy-booking")
        logger.info(f"📥 Headers ricevuti: {dict(request.headers)}")
        logger.info(f"📥 Content-Type: {request.content_type}")
        logger.info(f"📥 Method: {request.method}")
        
        # Prova a leggere i dati JSON
        try:
            data = request.get_json(force=True)  # force=True per sicurezza
            logger.info(f"📦 Dati JSON ricevuti: {data}")
            logger.info(f"📦 Tipo dati: {type(data)}")
        except Exception as json_error:
            logger.error(f"❌ Errore parsing JSON: {json_error}")
            logger.info(f"📦 Raw data: {request.get_data()}")
            return jsonify({'error': 'Dati JSON non validi', 'details': str(json_error)}), 400
        
        if not data:
            logger.error("❌ Nessun dato ricevuto")
            return jsonify({'error': 'Nessun dato ricevuto'}), 400
            
        # Estrai i parametri
        slot_scelto = data.get('slot_scelto')
        user_name = data.get('user_name')
        user_email = data.get('user_email')
        
        logger.info(f"🎯 slot_scelto: '{slot_scelto}' (type: {type(slot_scelto)})")
        logger.info(f"👤 user_name: '{user_name}' (type: {type(user_name)})")
        logger.info(f"📧 user_email: '{user_email}' (type: {type(user_email)})")

        # Validazione rigorosa
        if slot_scelto is None:
            logger.error("❌ slot_scelto è None")
            return jsonify({'error': 'slot_scelto è obbligatorio e non può essere None'}), 400
            
        if not user_name:
            logger.error(f"❌ user_name vuoto o None: '{user_name}'")
            return jsonify({'error': 'user_name è obbligatorio'}), 400
            
        if not user_email:
            logger.error(f"❌ user_email vuoto o None: '{user_email}'")
            return jsonify({'error': 'user_email è obbligatorio'}), 400

        # Controlla se lo slot è valido
        logger.info(f"🕐 TIME_SLOTS disponibili: {TIME_SLOTS}")
        
        if slot_scelto not in TIME_SLOTS:
            logger.error(f"❌ Slot non valido: '{slot_scelto}' non è in {TIME_SLOTS}")
            return jsonify({
                'error': 'slot_scelto non valido',
                'slot_ricevuto': slot_scelto,
                'slots_validi': TIME_SLOTS
            }), 400

        slot_id = TIME_SLOTS.index(slot_scelto)
        logger.info(f"✅ Slot ID trovato: {slot_id} per slot '{slot_scelto}'")

        # Costruisci documento MongoDB
        booking_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        doc = {
            "slot_id": slot_id,
            "time_slot": slot_scelto,
            "user_name": user_name,
            "user_email": user_email,
            "booking_date": booking_date,
            "status": "booked",
            "source": "ConvyAI",
            "raw_request": data  # Per debug
        }
        
        logger.info(f"📄 Documento da inserire in MongoDB: {doc}")

        # Test connessione MongoDB
        try:
            mongo_client.admin.command('ping')
            logger.info("✅ MongoDB ping riuscito")
            logger.info(f"🗄️ Database: {db.name}")
            logger.info(f"📝 Collection: quixa_callback")
        except Exception as ping_error:
            logger.error(f"❌ MongoDB ping fallito: {ping_error}")
            return jsonify({
                'error': 'MongoDB non raggiungibile', 
                'details': str(ping_error)
            }), 500

        # Inserimento in MongoDB
        try:
            logger.info("💾 Inizio inserimento in MongoDB...")
            result = quixa_collection.insert_one(doc)
            mongo_id = str(result.inserted_id)
            logger.info(f"✅ Documento inserito! MongoDB ID: {mongo_id}")
            
            # Verifica inserimento
            verification = quixa_collection.find_one({"_id": result.inserted_id})
            if verification:
                logger.info("✅ Documento verificato correttamente in MongoDB")
                # Rimuovi il campo raw_request dalla risposta
                verification.pop('raw_request', None)
                verification['_id'] = str(verification['_id'])
            else:
                logger.warning("⚠️ Documento non trovato dopo l'inserimento")
                
        except Exception as insert_error:
            logger.error(f"❌ Errore inserimento MongoDB: {insert_error}")
            logger.error(f"❌ Tipo errore: {type(insert_error)}")
            return jsonify({
                'error': 'Errore durante il salvataggio in MongoDB', 
                'details': str(insert_error)
            }), 500

        # Conta totale documenti per debug
        try:
            total_count = quixa_collection.count_documents({})
            logger.info(f"📊 Totale documenti nella collection: {total_count}")
        except Exception as count_error:
            logger.warning(f"⚠️ Errore conteggio documenti: {count_error}")

        # Risposta di successo
        response = {
            'status': 'success', 
            'message': '✅ Prenotazione salvata in MongoDB Atlas', 
            'booking': {
                'slot_id': slot_id,
                'time_slot': slot_scelto,
                'user_name': user_name,
                'user_email': user_email,
                'booking_date': booking_date
            },
            'mongodb_id': mongo_id,
            'database': db.name,
            'collection': 'quixa_callback'
        }
        
        logger.info(f"✅ Risposta finale: {response}")
        logger.info("="*50)
        
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"❌ ERRORE GENERALE: {e}")
        logger.error(f"❌ Tipo errore: {type(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'error': 'Errore interno del server', 
            'details': str(e)
        }), 500
        
@app.route('/email-exists', methods=['GET'])
def email_exists():
    email = request.args.get('email')
    if not email:
        return jsonify({'error': 'Parametro email mancante'}), 400
    try:
        exists = quixa_collection.find_one({'user_email': email, 'status': 'booked'}) is not None
        return jsonify({'exists': exists}), 200
    except Exception as e:
        logger.error(f"Errore email_exists: {e}")
        return jsonify({'error': str(e)}), 500

# ENDPOINT PER VEDERE TUTTE LE PRENOTAZIONI
@app.route('/bookings', methods=['GET'])
def get_all_bookings():
    try:
        # Da MongoDB
        mongo_bookings = list(quixa_collection.find({}).sort("booking_date", -1))
        for booking in mongo_bookings:
            booking['_id'] = str(booking['_id'])
            booking.pop('raw_request', None)  # Rimuovi dati di debug
            
        return jsonify({
            'status': 'success',
            'mongodb_count': len(mongo_bookings),
            'bookings': mongo_bookings
        }), 200
        
    except Exception as e:
        logger.error(f"Errore get_all_bookings: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/cancel', methods=['POST'])
def cancel_booking():
    try:
        data = request.get_json()
        
        user_email = data.get('user_email')

        if user_email is None :
            return jsonify({'error': ' user_email sono obbligatori'}), 400

        success, message = booking_service.cancel_booking(user_email)

        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                
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
