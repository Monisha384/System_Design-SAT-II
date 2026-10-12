from flask import Flask, request, jsonify
from threading import Lock, Thread
from queue import Queue
from datetime import datetime
from uuid import uuid4
import time

app = Flask(__name__)
lock = Lock()
event_queue = Queue()
cache = {}  # Demo cache; use Redis in a production deployment.

stations = [{"stationId": "ST101", "name": "City Charging Hub",
             "location": "Coimbatore", "chargerIds": ["CH101", "CH102"]}]
chargers = {
    "CH101": {"chargerId": "CH101", "stationId": "ST101", "status": "AVAILABLE", "powerKW": 22},
    "CH102": {"chargerId": "CH102", "stationId": "ST101", "status": "AVAILABLE", "powerKW": 50}
}
reservations, sessions = {}, {}


def event_worker():
    while True:
        event = event_queue.get()
        if event is None:
            break
        print("EVENT:", event)  # Replace with Kafka/RabbitMQ consumer in production.
        event_queue.task_done()


Thread(target=event_worker, daemon=True).start()


def publish_event(event_type, payload):
    event_queue.put({"type": event_type, "payload": payload,
                     "createdAt": datetime.now().isoformat(timespec="seconds")})


@app.get("/api/stations")
def search_stations():
    location = request.args.get("location", "").lower()
    key = "stations:" + location
    if key in cache:
        return jsonify(cache[key]), 200
    result = []
    for station in stations:
        if location and location not in station["location"].lower():
            continue
        result.append({"stationId": station["stationId"], "name": station["name"],
                       "location": station["location"],
                       "availableChargers": sum(
                           chargers[c]["status"] == "AVAILABLE" for c in station["chargerIds"])})
    response = {"stations": result}
    cache[key] = response
    return jsonify(response), 200


@app.get("/api/chargers/<charger_id>/availability")
def availability(charger_id):
    charger = chargers.get(charger_id)
    if not charger:
        return jsonify({"error": "CHARGER_NOT_FOUND"}), 404
    return jsonify({"chargerId": charger_id, "status": charger["status"],
                    "powerKW": charger["powerKW"]}), 200


@app.post("/api/reservations")
def reserve():
    data = request.get_json(silent=True) or {}
    uid, cid, start = data.get("userId"), data.get("chargerId"), data.get("startTime")
    if not uid or not cid or not start:
        return jsonify({"error": "userId, chargerId and startTime are required"}), 400
    with lock:
        charger = chargers.get(cid)
        if not charger:
            return jsonify({"error": "CHARGER_NOT_FOUND"}), 404
        if charger["status"] != "AVAILABLE":
            return jsonify({"error": "CHARGER_UNAVAILABLE"}), 409
        rid = "R" + uuid4().hex[:8].upper()
        reservations[rid] = {"reservationId": rid, "userId": uid, "chargerId": cid,
                             "startTime": start, "status": "CONFIRMED"}
        charger["status"] = "RESERVED"
        cache.clear()
    publish_event("ReservationCreated", reservations[rid])
    return jsonify(reservations[rid]), 201


@app.post("/api/sessions")
def start_session():
    data = request.get_json(silent=True) or {}
    rid = data.get("reservationId")
    if not rid:
        return jsonify({"error": "reservationId is required"}), 400
    with lock:
        reservation = reservations.get(rid)
        if not reservation or reservation["status"] != "CONFIRMED":
            return jsonify({"error": "RESERVATION_NOT_FOUND_OR_INVALID"}), 404
        sid, cid = "CS" + uuid4().hex[:8].upper(), reservation["chargerId"]
        sessions[sid] = {"sessionId": sid, "reservationId": rid, "userId": reservation["userId"],
                         "chargerId": cid, "status": "CHARGING",
                         "startTime": datetime.now().isoformat(timespec="seconds"),
                         "energyConsumedKWh": 0.0}
        reservation["status"] = "IN_PROGRESS"
        chargers[cid]["status"] = "CHARGING"
        cache.clear()
    publish_event("ChargingStarted", sessions[sid])
    return jsonify(sessions[sid]), 201


@app.get("/api/sessions/<sid>")
def get_session(sid):
    session = sessions.get(sid)
    if not session:
        return jsonify({"error": "SESSION_NOT_FOUND"}), 404
    return jsonify(session), 200


@app.post("/api/sessions/<sid>/end")
def end_session(sid):
    with lock:
        session = sessions.get(sid)
        if not session:
            return jsonify({"error": "SESSION_NOT_FOUND"}), 404
        if session["status"] != "CHARGING":
            return jsonify({"error": "SESSION_NOT_ACTIVE"}), 409
        session["status"] = "COMPLETED"
        session["endTime"] = datetime.now().isoformat(timespec="seconds")
        session["energyConsumedKWh"] = 18.5  # Demo value; replace with meter reading.
        chargers[session["chargerId"]]["status"] = "AVAILABLE"
        reservations[session["reservationId"]]["status"] = "COMPLETED"
        cache.clear()
    publish_event("ChargingCompleted", session)
    return jsonify({"sessionId": sid, "status": "COMPLETED",
                    "energyConsumedKWh": session["energyConsumedKWh"],
                    "message": "Charging session ended successfully"}), 200


@app.get("/health")
def health():
    return jsonify({"status": "UP", "service": "EV Charging API"}), 200


if __name__ == "__main__":
    # For local demonstration only. Production: multiple workers behind a load balancer,
    # shared PostgreSQL database, Redis cache, and Kafka/RabbitMQ.
    app.run(host="127.0.0.1", port=5001, debug=True)
