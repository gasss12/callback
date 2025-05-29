from flask import Flask, request, jsonify
import csv
import os
from datetime import datetime
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File CSV per memorizzare le prenotazioni
BOOKINGS_FILE = 'prenotazioni.csv'

# Porta per Render.com
PORT = int(os.environ.get('PORT', 5000))

# Slot di tempo disponibili
TIME_SLOTS = [
    "09:00-10:00",
    "10:00-11:00", 
    "11:00-12:00"
]

class BookingService:
    def __init__(self):
        self.init_csv_file()
    
    def init_csv_file(self):
        """Inizializza il file CSV se non esiste"""
        if not os.path.exists(BOOKINGS_FILE):
            with open(BOOKINGS_FILE, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['slot_id', 'time_slot', 'user_name', 'user_email', 'booking_date', 'status'])
            logger.info("File CSV inizializzato")
    
    def get_available_slots(self):
        """Restituisce gli slot disponibili"""
        booked_slots = []
        
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['status'] == 'booked':
                        booked_slots.append(int(row['slot_id']))
        except FileNotFoundError:
            pass
        
        available = []
        for i, slot in enumerate(TIME_SLOTS):
            if i not in booked_slots:
                available.append({
                    'slot_id': i,
                    'time_slot': slot,
                    'available': True
                })
        
        return available
    
    def get_all_slots_status(self):
        """Restituisce lo stato di tutti gli slot"""
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
        
        slots_status = []
        for i, slot in enumerate(TIME_SLOTS):
            if i in booked_slots:
                slots_status.append({
                    'slot_id': i,
                    'time_slot': slot,
                    'available': False,
                    'booked_by': booked_slots[i]
                })
            else:
                slots_status.append({
                    'slot_id': i,
                    'time_slot': slot,
                    'available': True
                })
        
        return slots_status
    
    def book_slot(self, slot_id, user_name, user_email):
        """Prenota uno slot"""
        if slot_id < 0 or slot_id >= len(TIME_SLOTS):
            return False, "Slot ID non valido"
        
        # Verifica se lo slot è già prenotato
        if not self.is_slot_available(slot_id):
            return False, "Slot già prenotato"
        
        # Aggiungi la prenotazione al CSV
        with open(BOOKINGS_FILE, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                slot_id,
                TIME_SLOTS[slot_id],
                user_name,
                user_email,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'booked'
            ])
        
        logger.info(f"Slot {slot_id} prenotato da {user_name}")
        return True, "Prenotazione confermata"
    
    def cancel_booking(self, slot_id, user_email):
        """Cancella una prenotazione"""
        if slot_id < 0 or slot_id >= len(TIME_SLOTS):
            return False, "Slot ID non valido"
        
        # Leggi tutte le prenotazioni
        rows = []
        booking_found = False
        
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if (int(row['slot_id']) == slot_id and 
                        row['user_email'] == user_email and 
                        row['status'] == 'booked'):
                        booking_found = True
                        logger.info(f"Cancellazione prenotazione slot {slot_id} per {user_email}")
                        # Non aggiungere questa riga (equivale a eliminarla)
                    else:
                        rows.append(row)
        except FileNotFoundError:
            return False, "Nessuna prenotazione trovata"
        
        if not booking_found:
            return False, "Prenotazione non trovata o email non corrispondente"
        
        # Riscrivi il file senza la prenotazione cancellata
        with open(BOOKINGS_FILE, 'w', newline='', encoding='utf-8') as file:
            if rows:
                fieldnames = rows[0].keys()
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            else:
                # Se non ci sono più righe, ricrea solo l'header
                writer = csv.writer(file)
                writer.writerow(['slot_id', 'time_slot', 'user_name', 'user_email', 'booking_date', 'status'])
        
        return True, "Prenotazione cancellata"
    
    def is_slot_available(self, slot_id):
        """Verifica se uno slot è disponibile"""
        try:
            with open(BOOKINGS_FILE, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if int(row['slot_id']) == slot_id and row['status'] == 'booked':
                        return False
        except FileNotFoundError:
            pass
        
        return True

# Istanza del servizio
booking_service = BookingService()

@app.route('/slots', methods=['GET'])
def get_slots():
    """Restituisce tutti gli slot con il loro stato"""
    try:
        slots = booking_service.get_all_slots_status()
        return jsonify({
            'status': 'success',
            'slots': slots,
            'total_slots': len(TIME_SLOTS)
        }), 200
    except Exception as e:
        logger.error(f"Errore get_slots: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/available', methods=['GET'])
def get_available():
    """Restituisce solo gli slot disponibili"""
    try:
        available = booking_service.get_available_slots()
        return jsonify({
            'status': 'success',
            'available_slots': available,
            'count': len(available)
        }), 200
    except Exception as e:
        logger.error(f"Errore get_available: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/book', methods=['POST'])
def book_slot():
    """Prenota uno slot"""
    try:
        data = request.get_json()
        
        slot_id = data.get('slot_id')
        user_name = data.get('user_name')
        user_email = data.get('user_email')
        
        if slot_id is None or not user_name or not user_email:
            return jsonify({
                'error': 'slot_id, user_name e user_email sono obbligatori'
            }), 400
        
        success, message = booking_service.book_slot(slot_id, user_name, user_email)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                'slot_id': slot_id,
                'time_slot': TIME_SLOTS[slot_id]
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Errore book_slot: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/cancel', methods=['POST'])
def cancel_booking():
    """Cancella una prenotazione"""
    try:
        data = request.get_json()
        
        slot_id = data.get('slot_id')
        user_email = data.get('user_email')
        
        if slot_id is None or not user_email:
            return jsonify({
                'error': 'slot_id e user_email sono obbligatori'
            }), 400
        
        success, message = booking_service.cancel_booking(slot_id, user_email)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message,
                'slot_id': slot_id,
                'time_slot': TIME_SLOTS[slot_id]
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Errore cancel_booking: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'WSCallback Booking System',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'available_slots': len(booking_service.get_available_slots())
    }), 200

@app.route('/', methods=['GET'])
def home():
    """Homepage con istruzioni"""
    instructions = {
        'service': 'WSCallback - Sistema Prenotazioni',
        'endpoints': {
            'GET /slots': 'Visualizza tutti gli slot con stato',
            'GET /available': 'Visualizza solo slot disponibili',
            'POST /book': 'Prenota uno slot (slot_id, user_name, user_email)',
            'POST /cancel': 'Cancella prenotazione (slot_id, user_email)',
            'GET /health': 'Health check del servizio'
        },
        'time_slots': TIME_SLOTS,
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
    }
    
    return jsonify(instructions), 200

if __name__ == '__main__':
    print("=== WSCallback - Sistema Prenotazioni ===")
    print("Slot disponibili:", TIME_SLOTS)
    print(f"Server in avvio su porta {PORT}")
    print("Usa GET / per vedere le istruzioni complete")
    app.run(debug=False, host='0.0.0.0', port=PORT)
